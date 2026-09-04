"""MedicineRequest API — create (guest/auth) + owner list/retrieve."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from storeApp.models import MedicineRequest, Notification

User = get_user_model()


class MedicineRequestApiTests(APITestCase):
    databases = {"default", "store"}

    def test_guest_create_without_image(self):
        res = self.client.post(
            "/api/store/medicine-requests/",
            {
                "full_name": "Binh",
                "phone": "0901234567",
                "note": "Can tu van",
                "items_json": json.dumps(
                    [{"product_id": 1, "product_name": "Paracetamol", "quantity": 1}]
                ),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["full_name"], "Binh")
        self.assertEqual(res.data["phone"], "0901234567")
        self.assertEqual(res.data["status"], MedicineRequest.PENDING)
        self.assertEqual(res.data["item_count"], 1)
        self.assertIsNone(res.data["prescription_image_url"])
        lead = MedicineRequest.objects.get(id=res.data["id"])
        self.assertIsNone(lead.user_id)
        note = Notification.objects.get(id=res.data["notification_id"])
        self.assertEqual(note.notification_type, Notification.ADMIN_SUPPORT)
        self.assertIn("Binh", note.title)

    def test_create_rejects_missing_phone(self):
        res = self.client.post(
            "/api/store/medicine-requests/",
            {"full_name": "Chi", "note": "x"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("phone", res.data)

    @patch("cloudinary.uploader.upload")
    def test_create_with_image_mocked(self, mock_upload):
        mock_upload.return_value = {
            "public_id": "OUPharmacy/medicine-requests/test",
            "version": 1,
            "format": "png",
            "resource_type": "image",
            "type": "upload",
        }
        # 1x1 PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        image = SimpleUploadedFile("don.png", png, content_type="image/png")
        res = self.client.post(
            "/api/store/medicine-requests/",
            {
                "full_name": "Anh",
                "phone": "0912345678",
                "prescription_image": image,
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        lead = MedicineRequest.objects.get(id=res.data["id"])
        self.assertTrue(bool(lead.prescription_image))

    def test_list_requires_auth(self):
        res = self.client.get("/api/store/medicine-requests/")
        self.assertEqual(res.status_code, 401)

    def test_list_and_retrieve_owner_only(self):
        owner = User.objects.create_user(
            email="med_owner@example.com",
            password="pass12345",
        )
        other = User.objects.create_user(
            email="med_other@example.com",
            password="pass12345",
        )
        own = MedicineRequest.objects.create(
            user_id=owner.id,
            full_name="Owner",
            phone="0901111111",
            note="mine",
        )
        MedicineRequest.objects.create(
            user_id=other.id,
            full_name="Other",
            phone="0902222222",
            note="theirs",
        )

        self.client.force_authenticate(user=owner)
        list_res = self.client.get("/api/store/medicine-requests/")
        self.assertEqual(list_res.status_code, 200)
        ids = [row["id"] for row in list_res.data]
        self.assertEqual(ids, [own.id])

        ok = self.client.get(f"/api/store/medicine-requests/{own.id}/")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["id"], own.id)

        other_lead = MedicineRequest.objects.exclude(user_id=owner.id).first()
        denied = self.client.get(f"/api/store/medicine-requests/{other_lead.id}/")
        self.assertEqual(denied.status_code, 403)


class ContactMedicineDelegatesToMedicineRequestTests(APITestCase):
    databases = {"default", "store"}

    def test_medicine_contact_creates_medicine_request(self):
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
        self.assertIn("medicine_request_id", res.data)
        lead = MedicineRequest.objects.get(id=res.data["medicine_request_id"])
        self.assertEqual(lead.full_name, "Binh")
        self.assertEqual(lead.phone, "0901234567")
        self.assertIn("Paracetamol", lead.note)
        note = Notification.objects.get(id=res.data["notification_id"])
        self.assertEqual(note.notification_type, Notification.ADMIN_SUPPORT)
