"""POST /api/store/contact/ — support vs medicine lead."""
from rest_framework.test import APITestCase

from storeApp.models import MedicineRequest, Notification


class ContactSupportRequestApiTests(APITestCase):
    databases = {"default", "store"}

    def test_support_requires_email(self):
        res = self.client.post(
            "/api/store/contact/",
            {"name": "An", "message": "Can help", "request_type": "support"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("email", res.data)

    def test_medicine_requires_phone_and_allows_missing_email(self):
        res = self.client.post(
            "/api/store/contact/",
            {
                "name": "Binh",
                "phone": "0901234567",
                "message": "Ghi chu\nSan pham:\n- 1 | Paracetamol | sl 1",
                "request_type": "medicine",
                "subject": "Can mua thuoc",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        lead = MedicineRequest.objects.get(id=res.data["medicine_request_id"])
        self.assertEqual(lead.phone, "0901234567")
        note = Notification.objects.get(id=res.data["notification_id"])
        self.assertEqual(note.notification_type, Notification.ADMIN_SUPPORT)
        self.assertIn("Binh", note.title)
        self.assertIn("0901234567", note.message)

    def test_medicine_rejects_missing_phone(self):
        res = self.client.post(
            "/api/store/contact/",
            {
                "name": "Chi",
                "message": "Can tu van",
                "request_type": "medicine",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("phone", res.data)
