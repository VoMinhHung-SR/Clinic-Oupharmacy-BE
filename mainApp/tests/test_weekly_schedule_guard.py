"""MASTER P2 — weekly schedule update must not CASCADE wipe booked exams."""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from mainApp.models import DoctorSchedule, Examination, Patient, TimeSlot, User


class WeeklyScheduleGuardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = User.objects.create_user(
            email="doctor-p2@example.com",
            password="Pass1234!",
        )
        self.booker = User.objects.create_user(
            email="booker-p2@example.com",
            password="Pass1234!",
        )
        self.patient = Patient.objects.create(
            first_name="P2",
            last_name="Patient",
            email="patient-p2@example.com",
            phone_number="0900222333",
        )
        self.client.force_authenticate(user=self.doctor)

        # ISO week in the future so dates are stable for the payload
        self.appt_date = timezone.localdate() + datetime.timedelta(days=14)
        self.week_str = self.appt_date.strftime("%G-W%V")
        self.week_start = datetime.datetime.strptime(self.week_str + "-1", "%G-W%V-%u").date()

        self.schedule = DoctorSchedule.objects.create(
            doctor=self.doctor,
            date=self.appt_date,
            session="morning",
            is_off=False,
        )

    def _weekly_payload(self, morning_off=False):
        days = {}
        for i in range(6):
            d = self.week_start + datetime.timedelta(days=i)
            days[d.isoformat()] = {
                "morning": {"session": "morning", "is_off": morning_off},
                "afternoon": {"session": "afternoon", "is_off": True},
            }
        return {"doctorID": self.doctor.id, "weekly_schedule": days}

    def test_update_blocked_when_week_has_bookings(self):
        slot = TimeSlot.objects.create(
            schedule=self.schedule,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
        )
        exam = Examination.objects.create(
            description="Booked",
            patient=self.patient,
            user=self.booker,
            time_slot=slot,
        )

        res = self.client.put(
            f"/doctor-schedules/update-weekly-schedule/?week={self.week_str}",
            self._weekly_payload(morning_off=True),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("errCode"), "HAS_BOOKINGS")
        self.assertTrue(Examination.objects.filter(pk=exam.pk).exists())
        self.assertTrue(DoctorSchedule.objects.filter(pk=self.schedule.pk).exists())
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    def test_update_allowed_when_week_has_no_bookings(self):
        schedule_id = self.schedule.id
        res = self.client.put(
            f"/doctor-schedules/update-weekly-schedule/?week={self.week_str}",
            self._weekly_payload(morning_off=False),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(DoctorSchedule.objects.filter(pk=schedule_id).exists())
        self.assertTrue(
            DoctorSchedule.objects.filter(
                doctor=self.doctor,
                date=self.appt_date,
                session="morning",
            ).exists()
        )
