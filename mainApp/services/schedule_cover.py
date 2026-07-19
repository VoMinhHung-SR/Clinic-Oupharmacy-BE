"""P5 — nurse-led cover: move examinations from doctor A session → doctor B (same specialty)."""
from django.db import transaction

from mainApp.models import DoctorProfile, DoctorSchedule, Examination, TimeSlot


class CoverError(Exception):
    def __init__(self, message, code="COVER_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


def _doctor_specialty_ids(doctor_id):
    try:
        profile = DoctorProfile.objects.get(user_id=doctor_id)
    except DoctorProfile.DoesNotExist:
        return set()
    return set(profile.specializations.values_list("id", flat=True))


def specialty_overlap(doctor_a_id, doctor_b_id):
    return bool(_doctor_specialty_ids(doctor_a_id) & _doctor_specialty_ids(doctor_b_id))


def _booked_hours_for_schedule(schedule):
    hours = []
    for slot in TimeSlot.objects.filter(schedule=schedule):
        if Examination.objects.filter(time_slot=slot, active=True).exists():
            hours.append((slot.start_time, slot.end_time))
    return hours


def list_cover_candidates(from_doctor_id, date, session):
    """Doctors sharing at least one specialty; annotate hour conflicts with A's booked slots."""
    from_tags = _doctor_specialty_ids(from_doctor_id)
    if not from_tags:
        return []

    try:
        from_schedule = DoctorSchedule.objects.get(
            doctor_id=from_doctor_id,
            date=date,
            session=session,
        )
    except DoctorSchedule.DoesNotExist:
        return []

    booked_starts = _booked_hours_for_schedule(from_schedule)

    profiles = (
        DoctorProfile.objects.filter(specializations__id__in=from_tags)
        .exclude(user_id=from_doctor_id)
        .select_related("user")
        .prefetch_related("specializations")
        .distinct()
    )

    results = []
    for profile in profiles:
        to_user = profile.user
        if not to_user or not to_user.is_active:
            continue
        to_schedule = DoctorSchedule.objects.filter(
            doctor_id=to_user.id,
            date=date,
            session=session,
            is_off=False,
        ).first()

        conflicts = []
        if to_schedule and booked_starts:
            existing = {
                (s.start_time, s.end_time)
                for s in TimeSlot.objects.filter(schedule=to_schedule)
            }
            for start, end in booked_starts:
                if (start, end) in existing:
                    conflicts.append({"start_time": str(start), "end_time": str(end)})

        results.append(
            {
                "doctorId": to_user.id,
                "email": to_user.email,
                "firstName": to_user.first_name,
                "lastName": to_user.last_name,
                "specializations": list(profile.specializations.values("id", "name")),
                "hasOpenSession": to_schedule is not None,
                "conflicts": conflicts,
                "canCover": len(conflicts) == 0,
            }
        )

    return sorted(results, key=lambda r: (not r["canCover"], r["lastName"] or ""))


@transaction.atomic
def reassign_session_cover(from_doctor_id, date, session, to_doctor_id):
    if int(from_doctor_id) == int(to_doctor_id):
        raise CoverError("from_doctor and to_doctor must differ", "INVALID_DOCTOR")

    if not specialty_overlap(from_doctor_id, to_doctor_id):
        raise CoverError(
            "Cover doctor must share at least one specialization",
            "SPECIALTY_MISMATCH",
        )

    try:
        from_schedule = DoctorSchedule.objects.select_for_update().get(
            doctor_id=from_doctor_id,
            date=date,
            session=session,
        )
    except DoctorSchedule.DoesNotExist as exc:
        raise CoverError("Source schedule session not found", "SOURCE_MISSING") from exc

    exams = list(
        Examination.objects.select_for_update()
        .filter(active=True, time_slot__schedule=from_schedule)
        .select_related("time_slot")
    )
    if not exams:
        raise CoverError("No active examinations to reassign on this session", "NO_EXAMS")

    to_schedule, _ = DoctorSchedule.objects.get_or_create(
        doctor_id=to_doctor_id,
        date=date,
        session=session,
        defaults={"is_off": False},
    )
    if to_schedule.is_off:
        to_schedule.is_off = False
        to_schedule.save(update_fields=["is_off"])

    to_schedule = DoctorSchedule.objects.select_for_update().get(pk=to_schedule.pk)

    existing_hours = {
        (s.start_time, s.end_time)
        for s in TimeSlot.objects.filter(schedule=to_schedule)
    }

    moved = []
    old_slots = []
    for exam in exams:
        slot = exam.time_slot
        if slot is None:
            raise CoverError(f"Examination {exam.id} has no time_slot", "MISSING_SLOT")
        key = (slot.start_time, slot.end_time)
        if key in existing_hours:
            raise CoverError(
                f"Target doctor already has {slot.start_time}-{slot.end_time}",
                "HOUR_CONFLICT",
            )
        new_slot = TimeSlot.objects.create(
            schedule=to_schedule,
            start_time=slot.start_time,
            end_time=slot.end_time,
            is_available=False,
        )
        existing_hours.add(key)
        exam.time_slot = new_slot
        exam.save()
        old_slots.append(slot)
        moved.append(exam.id)

    for old in old_slots:
        if not Examination.objects.filter(time_slot=old).exists():
            old.delete()

    from_pk = from_schedule.pk
    if not TimeSlot.objects.filter(schedule_id=from_pk).exists():
        DoctorSchedule.objects.filter(pk=from_pk).delete()

    return {
        "movedExaminationIds": moved,
        "toDoctorId": int(to_doctor_id),
        "toScheduleId": to_schedule.id,
        "fromScheduleClosed": not DoctorSchedule.objects.filter(pk=from_pk).exists(),
    }
