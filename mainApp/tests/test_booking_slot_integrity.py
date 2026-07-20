"""MASTER P1 — TimeSlot unique + examination book/destroy integrity."""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from mainApp.constant import MAX_EXAMINATION_PER_DAY
from mainApp.models import DoctorSchedule, Examination, Patient, TimeSlot, User


class BookingSlotIntegrityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="booker-p1@example.com",
            password="Pass1234!",
        )
        self.doctor = User.objects.create_user(
            email="doctor-p1@example.com",
            password="Pass1234!",
        )
        self.patient = Patient.objects.create(
            first_name="P1",
            last_name="Patient",
            email="patient-p1@example.com",
            phone_number="0900111222",
        )
        self.client.force_authenticate(user=self.user)

        # Future appointment day (avoid past-slot rejection)
        self.appt_date = timezone.localdate() + datetime.timedelta(days=3)
        self.schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            date=self.appt_date,
            session="morning",
            is_off=False,
        )
        self.start = datetime.time(9, 0, 0)
        self.end = datetime.time(10, 0, 0)

    def _create_slot(self, schedule=None, start=None, end=None):
        return TimeSlot.objects.create(
            schedule=schedule or self.schedule,
            start_time=start or self.start,
            end_time=end or self.end,
        )

    def test_duplicate_timeslot_rejected(self):
        first = self.client.post(
            "/time-slots/",
            {
                "schedule": self.schedule.id,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            "/time-slots/",
            {
                "schedule": self.schedule.id,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already taken", second.data.get("errMsg", "").lower())
        self.assertEqual(TimeSlot.objects.filter(schedule=self.schedule).count(), 1)

    def test_timeslot_on_off_schedule_rejected(self):
        off = DoctorSchedule.objects.create(
            doctor=self.doctor,
            date=self.appt_date,
            session="afternoon",
            is_off=True,
        )
        res = self.client.post(
            "/time-slots/",
            {
                "schedule": off.id,
                "start_time": "13:00:00",
                "end_time": "14:00:00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_exam_and_second_same_slot_rejected(self):
        slot = self._create_slot()
        first = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "Khám P1",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "Khám trùng",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_past_slot_rejected(self):
        past_date = timezone.localdate() - datetime.timedelta(days=1)
        past_schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            date=past_date,
            session="morning",
            is_off=False,
        )
        slot = self._create_slot(schedule=past_schedule)
        res = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "Past",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("past", res.data.get("errMsg", "").lower())

    def test_capacity_uses_schedule_date(self):
        # Fill capacity for appointment date via other hours
        for hour in range(MAX_EXAMINATION_PER_DAY):
            start = datetime.time(8 + (hour // 4), (hour % 4) * 15, 0)
            # keep unique starts within morning/afternoon; use sequence of minutes
            start = (datetime.datetime.combine(self.appt_date, datetime.time(0, 0))
                     + datetime.timedelta(minutes=hour)).time()
            end = (datetime.datetime.combine(self.appt_date, start)
                   + datetime.timedelta(minutes=1)).time()
            slot = TimeSlot.objects.create(
                schedule=self.schedule,
                start_time=start,
                end_time=end,
            )
            Examination.objects.create(
                description=f"fill-{hour}",
                patient=self.patient,
                user=self.user,
                time_slot=slot,
            )

        overflow_slot = TimeSlot.objects.create(
            schedule=self.schedule,
            start_time=datetime.time(11, 0, 0),
            end_time=datetime.time(12, 0, 0),
        )
        res = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "overflow",
                "time_slot": overflow_slot.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("maximum", res.data.get("errMsg", "").lower())

    def test_destroy_exam_frees_timeslot(self):
        slot = self._create_slot()
        create = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "Will cancel",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        exam_id = create.data["id"]
        slot_id = slot.id

        delete = self.client.delete(f"/examinations/{exam_id}/")
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Examination.objects.filter(pk=exam_id).exists())
        self.assertFalse(TimeSlot.objects.filter(pk=slot_id).exists())

        # Same hour can be booked again
        recreate_slot = self.client.post(
            "/time-slots/",
            {
                "schedule": self.schedule.id,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
            format="json",
        )
        self.assertEqual(recreate_slot.status_code, status.HTTP_201_CREATED)

    def test_create_exam_without_description(self):
        slot = self._create_slot(start=datetime.time(11, 0), end=datetime.time(12, 0))
        res = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data.get("description"), "")
        self.assertEqual(Examination.objects.get(pk=res.data["id"]).description, "")

    def test_create_exam_empty_description(self):
        slot = self._create_slot(start=datetime.time(12, 0), end=datetime.time(13, 0))
        res = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "   ",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data.get("description"), "")

    def test_patch_exam_clear_description(self):
        slot = self._create_slot(start=datetime.time(14, 0), end=datetime.time(15, 0))
        create = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "Has note",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        exam_id = create.data["id"]

        patch = self.client.patch(
            f"/examinations/{exam_id}/",
            {
                "patient": self.patient.id,
                "description": "",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertEqual(patch.data.get("description"), "")
        self.assertEqual(Examination.objects.get(pk=exam_id).description, "")

    def test_patch_exam_omit_description_keeps_prior(self):
        slot = self._create_slot(start=datetime.time(15, 0), end=datetime.time(16, 0))
        create = self.client.post(
            "/examinations/",
            {
                "patient": self.patient.id,
                "description": "Keep me",
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED)
        exam_id = create.data["id"]

        # API patch always requires patient + time_slot; omit description key only
        patch = self.client.patch(
            f"/examinations/{exam_id}/",
            {
                "patient": self.patient.id,
                "time_slot": slot.id,
            },
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertEqual(Examination.objects.get(pk=exam_id).description, "Keep me")
