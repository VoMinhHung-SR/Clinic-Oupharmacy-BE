"""MASTER P5 — nurse-led specialty cover reassignment."""
import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from mainApp.models import (
    DoctorProfile,
    DoctorSchedule,
    Examination,
    Patient,
    SpecializationTag,
    TimeSlot,
    User,
    UserRole,
)


class ScheduleCoverTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.nurse_role = UserRole.objects.create(name="ROLE_NURSE")
        self.doctor_role = UserRole.objects.create(name="ROLE_DOCTOR")
        self.tag = SpecializationTag.objects.create(name="Nội khoa-P5")

        self.nurse = User.objects.create_user(
            email="nurse-p5@example.com",
            password="Pass1234!",
            role=self.nurse_role,
        )
        self.doctor_a = User.objects.create_user(
            email="doctor-a-p5@example.com",
            password="Pass1234!",
            role=self.doctor_role,
            first_name="A",
            last_name="Doctor",
        )
        self.doctor_b = User.objects.create_user(
            email="doctor-b-p5@example.com",
            password="Pass1234!",
            role=self.doctor_role,
            first_name="B",
            last_name="Doctor",
        )
        self.doctor_c = User.objects.create_user(
            email="doctor-c-p5@example.com",
            password="Pass1234!",
            role=self.doctor_role,
            first_name="C",
            last_name="Other",
        )
        other_tag = SpecializationTag.objects.create(name="Da liễu-P5")

        pa = DoctorProfile.objects.create(user=self.doctor_a)
        pa.specializations.add(self.tag)
        pb = DoctorProfile.objects.create(user=self.doctor_b)
        pb.specializations.add(self.tag)
        pc = DoctorProfile.objects.create(user=self.doctor_c)
        pc.specializations.add(other_tag)

        self.booker = User.objects.create_user(email="booker-p5@example.com", password="Pass1234!")
        self.patient = Patient.objects.create(
            first_name="P5",
            last_name="Patient",
            email="patient-p5@example.com",
            phone_number="0900555666",
        )

        self.appt_date = timezone.localdate() + datetime.timedelta(days=10)
        self.schedule_a = DoctorSchedule.objects.create(
            doctor=self.doctor_a,
            date=self.appt_date,
            session="morning",
            is_off=False,
        )
        self.slot = TimeSlot.objects.create(
            schedule=self.schedule_a,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
        )
        self.exam = Examination.objects.create(
            description="Cover me",
            patient=self.patient,
            user=self.booker,
            time_slot=self.slot,
        )
        self.client.force_authenticate(user=self.nurse)

    def test_candidates_same_specialty_only(self):
        res = self.client.post(
            "/doctor-schedules/cover-candidates/",
            {
                "fromDoctorId": self.doctor_a.id,
                "date": self.appt_date.isoformat(),
                "session": "morning",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = {c["doctorId"] for c in res.data["candidates"]}
        self.assertIn(self.doctor_b.id, ids)
        self.assertNotIn(self.doctor_c.id, ids)
        self.assertNotIn(self.doctor_a.id, ids)

    def test_reassign_moves_exam_and_closes_source(self):
        res = self.client.post(
            "/doctor-schedules/cover-reassign/",
            {
                "fromDoctorId": self.doctor_a.id,
                "toDoctorId": self.doctor_b.id,
                "date": self.appt_date.isoformat(),
                "session": "morning",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.time_slot.schedule.doctor_id, self.doctor_b.id)
        self.assertFalse(DoctorSchedule.objects.filter(pk=self.schedule_a.pk).exists())

    def test_reassign_rejects_specialty_mismatch(self):
        res = self.client.post(
            "/doctor-schedules/cover-reassign/",
            {
                "fromDoctorId": self.doctor_a.id,
                "toDoctorId": self.doctor_c.id,
                "date": self.appt_date.isoformat(),
                "session": "morning",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("errCode"), "SPECIALTY_MISMATCH")

    def test_reassign_rejects_hour_conflict(self):
        schedule_b = DoctorSchedule.objects.create(
            doctor=self.doctor_b,
            date=self.appt_date,
            session="morning",
            is_off=False,
        )
        TimeSlot.objects.create(
            schedule=schedule_b,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
        )
        res = self.client.post(
            "/doctor-schedules/cover-reassign/",
            {
                "fromDoctorId": self.doctor_a.id,
                "toDoctorId": self.doctor_b.id,
                "date": self.appt_date.isoformat(),
                "session": "morning",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("errCode"), "HOUR_CONFLICT")
        self.assertTrue(Examination.objects.filter(pk=self.exam.pk, time_slot=self.slot).exists())
