"""MASTER P4 — weekly schedule diff (add/remove empty sessions only)."""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from mainApp.models import DoctorSchedule, Examination, Patient, TimeSlot, User


class WeeklyScheduleDiffTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = User.objects.create_user(
            email="doctor-p4@example.com",
            password="Pass1234!",
        )
        self.booker = User.objects.create_user(
            email="booker-p4@example.com",
            password="Pass1234!",
        )
        self.patient = Patient.objects.create(
            first_name="P4",
            last_name="Patient",
            email="patient-p4@example.com",
            phone_number="0900444555",
        )
        self.client.force_authenticate(user=self.doctor)

        self.appt_date = timezone.localdate() + datetime.timedelta(days=14)
        self.week_str = self.appt_date.strftime("%G-W%V")
        self.week_start = datetime.datetime.strptime(self.week_str + "-1", "%G-W%V-%u").date()

        self.morning = DoctorSchedule.objects.create(
            doctor=self.doctor,
            date=self.appt_date,
            session="morning",
            is_off=False,
        )
        self.afternoon = DoctorSchedule.objects.create(
            doctor=self.doctor,
            date=self.appt_date,
            session="afternoon",
            is_off=False,
        )

    def _weekly_payload(self, *, morning_off=False, afternoon_off=False):
        days = {}
        for i in range(6):
            d = self.week_start + datetime.timedelta(days=i)
            days[d.isoformat()] = {
                "morning": {
                    "session": "morning",
                    "is_off": morning_off if d == self.appt_date else True,
                },
                "afternoon": {
                    "session": "afternoon",
                    "is_off": afternoon_off if d == self.appt_date else True,
                },
            }
        # Keep morning open on appt day by default unless morning_off
        if not morning_off:
            days[self.appt_date.isoformat()]["morning"]["is_off"] = False
        if not afternoon_off:
            days[self.appt_date.isoformat()]["afternoon"]["is_off"] = False
        return {"doctorID": self.doctor.id, "weekly_schedule": days}

    def test_cannot_turn_off_session_with_booking(self):
        slot = TimeSlot.objects.create(
            schedule=self.morning,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
        )
        exam = Examination.objects.create(
            description="Booked morning",
            patient=self.patient,
            user=self.booker,
            time_slot=slot,
        )

        res = self.client.put(
            f"/doctor-schedules/update-weekly-schedule/?week={self.week_str}",
            self._weekly_payload(morning_off=True, afternoon_off=False),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("errCode"), "HAS_BOOKINGS")
        self.assertTrue(Examination.objects.filter(pk=exam.pk).exists())
        self.assertTrue(DoctorSchedule.objects.filter(pk=self.morning.pk).exists())

    def test_can_turn_off_empty_session_while_sibling_has_booking(self):
        TimeSlot.objects.create(
            schedule=self.morning,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
        )
        Examination.objects.create(
            description="Booked morning",
            patient=self.patient,
            user=self.booker,
            time_slot=TimeSlot.objects.get(schedule=self.morning),
        )
        afternoon_id = self.afternoon.id

        res = self.client.put(
            f"/doctor-schedules/update-weekly-schedule/?week={self.week_str}",
            self._weekly_payload(morning_off=False, afternoon_off=True),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(DoctorSchedule.objects.filter(pk=self.morning.pk).exists())
        self.assertFalse(DoctorSchedule.objects.filter(pk=afternoon_id).exists())

    def test_can_add_missing_open_session(self):
        self.afternoon.delete()
        res = self.client.put(
            f"/doctor-schedules/update-weekly-schedule/?week={self.week_str}",
            self._weekly_payload(morning_off=False, afternoon_off=False),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(
            DoctorSchedule.objects.filter(
                doctor=self.doctor,
                date=self.appt_date,
                session="afternoon",
            ).exists()
        )
        self.assertEqual(res.data.get("created"), 1)
