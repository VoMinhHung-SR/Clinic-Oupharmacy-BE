import datetime
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.decorators import action

from mainApp.authz import is_business_admin
from mainApp.constant import CLINIC_OPEN_WEEKDAYS, CLINIC_SESSIONS, ROLE_NURSE
from mainApp.models import DoctorSchedule, TimeSlot, User, Examination
from mainApp.serializers import DoctorScheduleSerializer, TimeSlotSerializer
from mainApp.services.schedule_cover import (
    CoverError,
    list_cover_candidates,
    reassign_session_cover,
)


def _actor_is_nurse(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_business_admin(user):
        return True
    role = getattr(user, "role", None)
    return bool(role and getattr(role, "name", None) == ROLE_NURSE)


def _date_in_clinic_frame(d):
    return d.weekday() in CLINIC_OPEN_WEEKDAYS


class DoctorScheduleViewSet(viewsets.ViewSet, generics.CreateAPIView,
                  generics.DestroyAPIView, generics.RetrieveAPIView,
                  generics.UpdateAPIView, generics.ListAPIView):
    queryset = DoctorSchedule.objects.all().order_by('-date')
    serializer_class = DoctorScheduleSerializer
    parser_classes = [JSONParser, MultiPartParser]

    @action(methods=['post'], detail=False, url_path='schedule')
    def get_schedule_by_date(self, request):
        date_str = request.data.get('date')
        doctor_id = request.data.get('doctor')
        try:
            if date_str and doctor_id:
                date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                doctor_data = DoctorSchedule.objects.filter(doctor=doctor_id, date=date).all()
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST,
                                data={"errMsg": "Can't get data, doctor or date is false"})

        except Exception as error:
            print(error)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"errMsg": "Cant get data doctor or date is false"})

        if doctor_data:
            doctor_data_serialized = DoctorScheduleSerializer(doctor_data, context={'request': request},
                                                              many=True).data
            for doctor in doctor_data_serialized:
                time_slots = TimeSlot.objects.filter(schedule=doctor['id']).all()
                doctor['time_slots'] = TimeSlotSerializer(time_slots, context={'request': request}, many=True).data

            return Response(
                data=doctor_data_serialized,
                status=status.HTTP_200_OK
            )
        return Response(data=[], status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False, url_path='create-weekly-schedule')
    def create_weekly_schedule(self, request):
        doctor_id = request.data.get('doctorID')
        weekly_schedule = request.data.get('weekly_schedule')

        if not doctor_id or not weekly_schedule:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                            data={"errMsg": "Missing required parameters"})

        try:
            for date_str, sessions in weekly_schedule.items():
                current_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                if not _date_in_clinic_frame(current_date):
                    continue
                for session_name, session_info in sessions.items():
                    session = session_info.get('session')
                    is_off = session_info.get('is_off', False)
                    if is_off:
                        continue
                    if session not in CLINIC_SESSIONS:
                        continue

                    if DoctorSchedule.objects.filter(
                        doctor_id=doctor_id,
                        date=current_date,
                        session=session,
                    ).exists():
                        continue

                    DoctorSchedule.objects.create(
                        doctor_id=doctor_id,
                        date=current_date,
                        session=session,
                        is_off=is_off
                    )

            return Response(status=status.HTTP_201_CREATED, data={"msg": "Weekly schedule created successfully"})
        except Exception as error:
            print(error)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"errMsg": "Error creating weekly schedule"})

    @action(methods=['get'], detail=False, url_path='doctor-stats')
    def get_doctor_stats(self, request):
        week_str = request.query_params.get('week')
        if not week_str:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"errMsg": "Missing required parameter: week"})

        try:
            week_start = datetime.datetime.strptime(week_str + '-1', '%G-W%V-%u').date()
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"errMsg": "Invalid week format. Use YYYY-Www"})

        try:
            doctors = User.objects.filter(role__name='ROLE_DOCTOR').all()
            doctor_stats = []
            total_counts = [0] * 7

            for doctor in doctors:
                schedule_counts = [0] * 7
                for i in range(7):
                    day = week_start + datetime.timedelta(days=i)
                    time_slot_count = TimeSlot.objects.filter(schedule__doctor=doctor, schedule__date=day).count()
                    schedule_counts[i] = time_slot_count
                    total_counts[i] += time_slot_count

                doctor_stats.append({
                    'label': f"{doctor.first_name} {doctor.last_name}",
                    'data': schedule_counts
                })

            doctor_stats.append({
                'label': 'Total Appointments',
                'data': total_counts
            })

            return Response(data=doctor_stats, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"errMsg": "Doctor or schedule not found"})

        except ValidationError as ve:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"errMsg": str(ve)})

        except Exception:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"errMsg": "Internal server error"})

    @action(methods=['get'], detail=False, url_path='check-weekly-schedule')
    def check_weekly_schedule(self, request):
        week_str = request.query_params.get('week')
        doctor_id = request.query_params.get('doctor_id')

        if not week_str:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                          data={"errMsg": "Missing required parameter: week"})

        try:
            week_start = datetime.datetime.strptime(week_str + '-1', '%G-W%V-%u').date()
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                          data={"errMsg": "Invalid week format. Use YYYY-Www"})

        try:
            if doctor_id:
                doctors = User.objects.filter(role__name='ROLE_DOCTOR', id=doctor_id).all()
            else:
                doctors = User.objects.filter(role__name='ROLE_DOCTOR').all()

            weekly_schedule = {}

            for doctor in doctors:
                doctor_schedule = {}
                for i in range(7):
                    current_date = week_start + datetime.timedelta(days=i)
                    date_str = current_date.strftime('%Y-%m-%d')

                    schedules = DoctorSchedule.objects.filter(
                        doctor=doctor,
                        date=current_date
                    ).all()

                    day_schedule = {}
                    for schedule in schedules:
                        time_slots = TimeSlot.objects.filter(schedule=schedule).all()
                        day_schedule[schedule.session] = {
                            'session': schedule.session,
                            'is_off': schedule.is_off,
                            'time_slots': TimeSlotSerializer(time_slots, many=True).data
                        }

                    doctor_schedule[date_str] = day_schedule

                weekly_schedule[doctor.email] = doctor_schedule

            return Response(data=weekly_schedule, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND,
                          data={"errMsg": "Doctor not found"})

        except ValidationError as ve:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                          data={"errMsg": str(ve)})

        except Exception:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          data={"errMsg": "Internal server error"})

    @action(methods=['put'], detail=False, url_path='update-weekly-schedule')
    def update_weekly_schedule(self, request):
        doctor_id = request.data.get('doctorID')
        weekly_schedule = request.data.get('weekly_schedule')
        week_str = request.query_params.get('week')

        if not all([doctor_id, weekly_schedule, week_str]):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Missing required parameters"}
            )

        try:
            week_start = datetime.datetime.strptime(week_str + '-1', '%G-W%V-%u').date()
            week_end = week_start + datetime.timedelta(days=6)

            # Desired OPEN sessions (P4 diff + P6 clinic frame).
            desired_open = set()
            for date_str, sessions in weekly_schedule.items():
                current_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                if current_date < week_start or current_date > week_end:
                    continue
                if not _date_in_clinic_frame(current_date):
                    continue
                for session_name, session_info in (sessions or {}).items():
                    session = (session_info or {}).get('session') or session_name
                    is_off = (session_info or {}).get('is_off', False)
                    if session in CLINIC_SESSIONS and not is_off:
                        desired_open.add((current_date, session))

            existing = list(
                DoctorSchedule.objects.filter(
                    doctor_id=doctor_id,
                    date__range=[week_start, week_end],
                )
            )

            to_delete = []
            blocked_sessions = []
            for schedule in existing:
                key = (schedule.date, schedule.session)
                if key in desired_open:
                    continue
                has_exam = Examination.objects.filter(
                    active=True,
                    time_slot__schedule_id=schedule.id,
                ).exists()
                if has_exam:
                    blocked_sessions.append({
                        "date": schedule.date.isoformat(),
                        "session": schedule.session,
                        "scheduleId": schedule.id,
                    })
                else:
                    to_delete.append(schedule)

            if blocked_sessions:
                return Response(
                    status=status.HTTP_400_BAD_REQUEST,
                    data={
                        "errMsg": (
                            "Cannot turn off sessions that still have booked examinations. "
                            "Cancel or reassign those bookings first."
                        ),
                        "errCode": "HAS_BOOKINGS",
                        "bookedCount": len(blocked_sessions),
                        "blockedSessions": blocked_sessions,
                    },
                )

            existing_keys = {(s.date, s.session) for s in existing}
            to_create_keys = desired_open - existing_keys

            created = []
            with transaction.atomic():
                for schedule in to_delete:
                    schedule.delete()
                for date, session in sorted(to_create_keys, key=lambda x: (x[0], x[1])):
                    created.append(
                        DoctorSchedule.objects.create(
                            doctor_id=doctor_id,
                            date=date,
                            session=session,
                            is_off=False,
                        )
                    )

            return Response(
                status=status.HTTP_200_OK,
                data={
                    "msg": "Weekly schedule updated successfully",
                    "created": len(created),
                    "deleted": len(to_delete),
                    "updated_schedules": len(desired_open),
                },
            )

        except ValueError:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Invalid week format"}
            )
        except Exception as error:
            print(error)
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"errMsg": "Error updating weekly schedule"}
            )

    @action(methods=['post'], detail=False, url_path='cover-candidates')
    def cover_candidates(self, request):
        """P5: list same-specialty doctors who can cover a session."""
        if not _actor_is_nurse(request.user):
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"errMsg": "Only nurse/staff can list cover candidates"},
            )
        from_doctor_id = request.data.get('fromDoctorId') or request.data.get('from_doctor_id')
        date_str = request.data.get('date')
        session = request.data.get('session')
        if not all([from_doctor_id, date_str, session]):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "fromDoctorId, date, session are required"},
            )
        if session not in CLINIC_SESSIONS:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Invalid session"},
            )
        try:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Invalid date format"},
            )
        candidates = list_cover_candidates(from_doctor_id, date, session)
        return Response(data={"candidates": candidates}, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False, url_path='cover-reassign')
    def cover_reassign(self, request):
        """P5: nurse moves all exams on A's session to B (specialty + no hour conflict)."""
        if not _actor_is_nurse(request.user):
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"errMsg": "Only nurse/staff can reassign cover"},
            )
        from_doctor_id = request.data.get('fromDoctorId') or request.data.get('from_doctor_id')
        to_doctor_id = request.data.get('toDoctorId') or request.data.get('to_doctor_id')
        date_str = request.data.get('date')
        session = request.data.get('session')
        if not all([from_doctor_id, to_doctor_id, date_str, session]):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "fromDoctorId, toDoctorId, date, session are required"},
            )
        if session not in CLINIC_SESSIONS:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Invalid session"},
            )
        try:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Invalid date format"},
            )
        try:
            result = reassign_session_cover(from_doctor_id, date, session, to_doctor_id)
        except CoverError as err:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": err.message, "errCode": err.code},
            )
        return Response(
            status=status.HTTP_200_OK,
            data={"msg": "Cover reassignment successful", **result},
        )
