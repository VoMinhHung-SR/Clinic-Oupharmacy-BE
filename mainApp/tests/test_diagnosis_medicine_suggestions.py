"""Tests for diagnosis-aware medicine suggestions (Phase 2 P0)."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from mainApp.models import Diagnosis, Examination, Patient, Prescribing, PrescriptionDetail, User
from mainApp.services.diagnosis_medicine_suggestions import (
    combined_diagnosis_similarity,
    get_diagnosis_medicine_suggestions,
    normalize_tokens,
)
from storeApp.models import Category, Product, ProductVariant, ProductVariantUnit


class DiagnosisSimilarityTests(TestCase):
    def test_normalize_tokens_strips_stopwords_and_accents(self):
        tokens = normalize_tokens("Viêm họng cấp và sốt")
        self.assertIn("viem", tokens)
        self.assertIn("hong", tokens)
        self.assertNotIn("va", tokens)

    def test_combined_similarity_identical_diagnosis(self):
        sim = combined_diagnosis_similarity(
            "sốt ho",
            "Viêm họng cấp",
            "sốt ho",
            "Viêm họng cấp",
        )
        self.assertGreaterEqual(sim, 0.99)

    def test_combined_similarity_unrelated(self):
        sim = combined_diagnosis_similarity(
            "đau bụng",
            "Viêm dạ dày",
            "gãy xương",
            "Gãy kín xương đùi",
        )
        self.assertLess(sim, 0.35)


class DiagnosisMedicineSuggestionsServiceTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.doctor = User.objects.create_user(
            email="doctor-suggest@example.com",
            password="Pass1234!",
        )
        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            email="patient@example.com",
            phone_number="0900000001",
        )
        self.examination = Examination.objects.create(
            description="Khám test",
            patient=self.patient,
            user=self.doctor,
        )

        self.category = Category.objects.create(name="Thuốc", slug="thuoc-test")
        self.product = Product.objects.create(
            name="Paracetamol 500mg",
            web_name="Paracetamol 500mg",
            slug="paracetamol-500",
            category=self.category,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packing="Vỉ",
            is_published=True,
            active=True,
            in_stock=10,
        )
        self.unit = ProductVariantUnit.objects.create(
            variant=self.variant,
            unit_name="Vỉ",
            quantity_in_base=1,
            price_value=15000,
            is_default=True,
            is_published=True,
        )

        self.past_diagnosis = Diagnosis.objects.create(
            sign="sốt ho khan",
            diagnosed="Viêm họng cấp",
            examination=self.examination,
            user=self.doctor,
            patient=self.patient,
        )
        past_prescribing = Prescribing.objects.create(
            diagnosis=self.past_diagnosis,
            user=self.doctor,
        )
        PrescriptionDetail.objects.create(
            prescribing=past_prescribing,
            quantity=2,
            uses="1 viên x 3 lần/ngày",
            product_variant_id=self.variant.id,
            product_variant_unit_id=self.unit.id,
        )

        self.current_diagnosis = Diagnosis.objects.create(
            sign="ho khan",
            diagnosed="Viêm họng",
            examination=self.examination,
            user=self.doctor,
            patient=self.patient,
        )

    def test_similar_diagnosis_returns_suggestions(self):
        data = get_diagnosis_medicine_suggestions(self.current_diagnosis.id, self.doctor.id)
        self.assertGreaterEqual(data["meta"]["matched_diagnoses"], 1)
        self.assertEqual(len(data["suggestions"]), 1)
        entry = data["suggestions"][0]
        self.assertEqual(entry["product_variant_id"], self.variant.id)
        self.assertTrue(entry["prefill_allowed"])
        self.assertEqual(entry["uses"], "1 viên x 3 lần/ngày")
        self.assertEqual(entry["quantity"], 2)

    def test_no_match_returns_empty_suggestions(self):
        unrelated = Diagnosis.objects.create(
            sign="đau đầu",
            diagnosed="Migraine",
            examination=self.examination,
            user=self.doctor,
            patient=self.patient,
        )
        data = get_diagnosis_medicine_suggestions(unrelated.id, self.doctor.id)
        self.assertEqual(data["suggestions"], [])

    def test_out_of_stock_variant_excluded(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(in_stock=0)
        data = get_diagnosis_medicine_suggestions(self.current_diagnosis.id, self.doctor.id)
        self.assertEqual(data["suggestions"], [])

    def test_unpublished_variant_excluded(self):
        ProductVariant.objects.filter(pk=self.variant.pk).update(is_published=False)
        data = get_diagnosis_medicine_suggestions(self.current_diagnosis.id, self.doctor.id)
        self.assertEqual(data["suggestions"], [])

    def test_missing_diagnosis_raises(self):
        with self.assertRaises(Diagnosis.DoesNotExist):
            get_diagnosis_medicine_suggestions(999999, self.doctor.id)


class DiagnosisMedicineSuggestionsApiTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.client = APIClient()
        self.doctor = User.objects.create_user(
            email="doctor-api@example.com",
            password="Pass1234!",
        )
        self.client.force_authenticate(user=self.doctor)
        self.patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            email="api-patient@example.com",
            phone_number="0900000002",
        )
        self.examination = Examination.objects.create(
            description="Khám api",
            patient=self.patient,
            user=self.doctor,
        )
        self.diagnosis = Diagnosis.objects.create(
            sign="ho",
            diagnosed="Viêm họng",
            examination=self.examination,
            user=self.doctor,
            patient=self.patient,
        )

    def test_requires_authentication(self):
        client = APIClient()
        response = client.get(
            f"/prescribing/medicine-suggestions/?diagnosis_id={self.diagnosis.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requires_diagnosis_id(self):
        response = self.client.get("/prescribing/medicine-suggestions/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_diagnosis_returns_404(self):
        response = self.client.get("/prescribing/medicine-suggestions/?diagnosis_id=999999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(
        "mainApp.viewsets.prescribing.get_diagnosis_medicine_suggestions",
        return_value={
            "diagnosis": {"id": 1, "sign": "a", "diagnosed": "b", "updated_at": None},
            "suggestions": [],
            "meta": {"scope": "doctor", "matched_diagnoses": 0},
        },
    )
    def test_success_response_shape(self, _mock):
        response = self.client.get(
            f"/prescribing/medicine-suggestions/?diagnosis_id={self.diagnosis.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("diagnosis", response.data)
        self.assertIn("suggestions", response.data)
        self.assertIn("meta", response.data)
