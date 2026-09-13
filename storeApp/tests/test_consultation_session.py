"""ConsultationSession API — create/list authz + atomic pharmacist claim."""
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import connections
from rest_framework.test import APITestCase

from mainApp.constant import ROLE_PHARMACIST, ROLE_USER
from mainApp.models import UserRole
from storeApp.models.consultation import ConsultationSession
from storeApp.services.consultation import pharmacist_queue

User = get_user_model()

BASE = "/api/store/consultation-sessions/"


class ConsultationSessionApiTests(APITestCase):
    databases = {"default", "store"}

    @classmethod
    def setUpTestData(cls):
        cls.user_role, _ = UserRole.objects.get_or_create(name=ROLE_USER, defaults={"active": True})
        cls.pharmacist_role, _ = UserRole.objects.get_or_create(
            name=ROLE_PHARMACIST, defaults={"active": True}
        )

    def setUp(self):
        self.customer = User.objects.create_user(
            email="consult_customer@example.com",
            password="pass12345",
            role=self.user_role,
        )
        self.other = User.objects.create_user(
            email="consult_other@example.com",
            password="pass12345",
            role=self.user_role,
        )
        self.pharmacist = User.objects.create_user(
            email="consult_pharmacist@example.com",
            password="pass12345",
            role=self.pharmacist_role,
        )
        self.pharmacist2 = User.objects.create_user(
            email="consult_pharmacist2@example.com",
            password="pass12345",
            role=self.pharmacist_role,
        )

    def test_create_requires_auth(self):
        res = self.client.post(BASE, {"need_text": "Ho khan"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_customer_create_and_list_mine(self):
        self.client.force_authenticate(user=self.customer)
        create = self.client.post(
            BASE,
            {"need_text": "Ho khan", "context_json": {"source": "product", "product_id": 12}},
            format="json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        self.assertEqual(create.data["user_id"], self.customer.id)
        self.assertEqual(create.data["status"], ConsultationSession.WAITING_FOR_PROFESSIONAL)
        self.assertIsNone(create.data["pharmacist_id"])
        self.assertEqual(create.data["need_text"], "Ho khan")
        self.assertEqual(create.data["context_json"]["product_id"], 12)

        ConsultationSession.objects.create(
            user_id=self.other.id,
            need_text="other session",
        )

        listed = self.client.get(BASE)
        self.assertEqual(listed.status_code, 200)
        ids = [row["id"] for row in listed.data]
        self.assertEqual(ids, [create.data["id"]])

    def test_customer_cannot_list_queue(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.get(BASE, {"scope": "queue"})
        self.assertEqual(res.status_code, 403)

    def test_customer_cannot_retrieve_others(self):
        session = ConsultationSession.objects.create(
            user_id=self.other.id,
            need_text="private",
        )
        self.client.force_authenticate(user=self.customer)
        res = self.client.get(f"{BASE}{session.id}/")
        self.assertEqual(res.status_code, 403)

    def test_pharmacist_queue_and_claim(self):
        session = ConsultationSession.objects.create(
            user_id=self.customer.id,
            need_text="Can tu van",
        )
        self.client.force_authenticate(user=self.pharmacist)
        queue = self.client.get(BASE, {"scope": "queue"})
        self.assertEqual(queue.status_code, 200)
        self.assertEqual([row["id"] for row in queue.data], [session.id])

        claim = self.client.post(f"{BASE}{session.id}/claim/")
        self.assertEqual(claim.status_code, 200, claim.data)
        self.assertEqual(claim.data["status"], ConsultationSession.IN_PROGRESS)
        self.assertEqual(claim.data["pharmacist_id"], self.pharmacist.id)

        session.refresh_from_db()
        self.assertEqual(session.pharmacist_id, self.pharmacist.id)
        self.assertEqual(session.status, ConsultationSession.IN_PROGRESS)

        # Second claim must fail
        self.client.force_authenticate(user=self.pharmacist2)
        again = self.client.post(f"{BASE}{session.id}/claim/")
        self.assertEqual(again.status_code, 400)

    def test_non_pharmacist_cannot_claim(self):
        session = ConsultationSession.objects.create(user_id=self.customer.id)
        self.client.force_authenticate(user=self.customer)
        res = self.client.post(f"{BASE}{session.id}/claim/")
        self.assertEqual(res.status_code, 403)

    def test_complete_and_cancel(self):
        session = ConsultationSession.objects.create(
            user_id=self.customer.id,
            pharmacist_id=self.pharmacist.id,
            status=ConsultationSession.IN_PROGRESS,
        )
        self.client.force_authenticate(user=self.pharmacist)
        done = self.client.post(f"{BASE}{session.id}/complete/")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.data["status"], ConsultationSession.COMPLETED)

        waiting = ConsultationSession.objects.create(user_id=self.customer.id)
        self.client.force_authenticate(user=self.customer)
        cancel = self.client.post(f"{BASE}{waiting.id}/cancel/")
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.data["status"], ConsultationSession.CANCELLED)

    def test_claim_rejects_already_claimed(self):
        """Atomic claim: second pharmacist loses (service-level; API covered above)."""
        session = ConsultationSession.objects.create(
            user_id=self.customer.id,
            need_text="race",
        )
        first = pharmacist_queue.claim_session(
            session_id=session.id,
            pharmacist_id=self.pharmacist.id,
        )
        self.assertEqual(first.pharmacist_id, self.pharmacist.id)
        self.assertEqual(first.status, ConsultationSession.IN_PROGRESS)

        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            pharmacist_queue.claim_session(
                session_id=session.id,
                pharmacist_id=self.pharmacist2.id,
            )

        session.refresh_from_db()
        self.assertEqual(session.pharmacist_id, self.pharmacist.id)
        self.assertEqual(session.status, ConsultationSession.IN_PROGRESS)

    @unittest.skipUnless(
        "postgresql" in settings.DATABASES.get("store", {}).get("ENGINE", ""),
        "Concurrent select_for_update race needs PostgreSQL",
    )
    def test_claim_race_only_one_wins(self):
        session = ConsultationSession.objects.create(
            user_id=self.customer.id,
            need_text="race",
        )
        session_id = session.id
        winners = []

        def try_claim(pharmacist_id):
            try:
                claimed = pharmacist_queue.claim_session(
                    session_id=session_id,
                    pharmacist_id=pharmacist_id,
                )
                return ("ok", claimed.pharmacist_id)
            except Exception as exc:
                return ("err", str(exc))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(try_claim, self.pharmacist.id),
                pool.submit(try_claim, self.pharmacist2.id),
            ]
            for fut in as_completed(futures):
                winners.append(fut.result())

        oks = [w for w in winners if w[0] == "ok"]
        errs = [w for w in winners if w[0] == "err"]
        self.assertEqual(len(oks), 1, winners)
        self.assertEqual(len(errs), 1, winners)
        session.refresh_from_db()
        self.assertEqual(session.status, ConsultationSession.IN_PROGRESS)
        self.assertEqual(session.pharmacist_id, oks[0][1])
