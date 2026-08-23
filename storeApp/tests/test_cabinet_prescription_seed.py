from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from mainApp.models import Diagnosis, Examination, Patient, Prescribing, PrescriptionDetail
from storeApp.models import Category, Product, ProductVariant, ProductVariantUnit


class CabinetPrescriptionSeedApiTests(APITestCase):
    databases = {"default", "store"}

    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="rx-cabinet-owner@example.com",
            password="test-pass-123",
        )
        self.other = user_model.objects.create_user(
            email="rx-cabinet-other@example.com",
            password="test-pass-123",
        )
        self.doctor = user_model.objects.create_user(
            email="rx-cabinet-doctor@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(user=self.owner)

        self.patient = Patient.objects.create(
            first_name="Owner",
            last_name="Patient",
            email="rx-owner-patient@example.com",
            phone_number="0900111222",
            user=self.owner,
        )
        self.examination = Examination.objects.create(
            description="Khám",
            patient=self.patient,
            user=self.owner,
        )
        self.diagnosis = Diagnosis.objects.create(
            sign="Sốt",
            diagnosed="Viêm họng",
            examination=self.examination,
            user=self.doctor,
            patient=self.patient,
        )
        self.prescribing = Prescribing.objects.create(
            diagnosis=self.diagnosis,
            user=self.doctor,
        )

        category = Category.objects.create(name="Rx Vitamin", slug="rx-vitamin")
        product = Product.objects.create(
            name="Rx Vitamin C",
            mid="MID-RX-001",
            slug="rx-vitamin-c",
            category=category,
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp 30 viên",
            sku="RX-VIT-C",
            in_stock=20,
            is_published=True,
            active=True,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            quantity_in_base=30,
            unit_name="Hộp",
            unit_order=0,
            price_value=50000,
            is_default=True,
            is_published=True,
        )

        self.detail = PrescriptionDetail.objects.create(
            prescribing=self.prescribing,
            quantity=2,
            uses="Ngày 2 lần",
            product_variant_id=self.variant.id,
            product_variant_unit_id=self.unit.id,
            item_name_snapshot="Rx Vitamin C",
            unit_name_snapshot="Hộp",
        )
        self.orphan = PrescriptionDetail.objects.create(
            prescribing=self.prescribing,
            quantity=1,
            uses="Khi đau",
            product_variant_id=None,
            product_variant_unit_id=None,
            item_name_snapshot="Thuốc ngoài catalog",
            unit_name_snapshot="Viên",
        )

        other_patient = Patient.objects.create(
            first_name="Other",
            last_name="Patient",
            email="rx-other-patient@example.com",
            phone_number="0900333444",
            user=self.other,
        )
        other_exam = Examination.objects.create(
            description="Khám other",
            patient=other_patient,
            user=self.other,
        )
        other_dx = Diagnosis.objects.create(
            sign="Ho",
            diagnosed="Viêm phế quản",
            examination=other_exam,
            user=self.doctor,
            patient=other_patient,
        )
        other_rx = Prescribing.objects.create(diagnosis=other_dx, user=self.doctor)
        PrescriptionDetail.objects.create(
            prescribing=other_rx,
            quantity=9,
            uses="Ngày 1 lần",
            product_variant_id=self.variant.id,
            product_variant_unit_id=self.unit.id,
            item_name_snapshot="Secret line",
        )

    def test_unauthenticated_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/store/cabinet-prescription-lines/")
        self.assertEqual(response.status_code, 401)

    def test_owner_sees_own_lines_only(self):
        response = self.client.get("/api/store/cabinet-prescription-lines/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        titles = {row["item_name"] for row in response.data}
        self.assertIn("Rx Vitamin C", titles)
        self.assertIn("Thuốc ngoài catalog", titles)
        self.assertNotIn("Secret line", titles)

        available = next(row for row in response.data if row["id"] == self.detail.id)
        self.assertTrue(available["variant_available"])
        self.assertEqual(available["product_variant_id"], self.variant.id)
        self.assertEqual(available["product_variant_unit_id"], self.unit.id)

        orphan = next(row for row in response.data if row["id"] == self.orphan.id)
        self.assertFalse(orphan["variant_available"])

    def test_other_user_does_not_see_owner_lines(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get("/api/store/cabinet-prescription-lines/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["item_name"], "Secret line")
