"""Public campaign preview tokens (D-19)."""

import time
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from storeApp.models import Campaign
from storeApp.services.campaign_cache import get_cached
from storeApp.services.campaign_preview import (
    sign_campaign_preview,
    unsign_campaign_preview,
)


class CampaignPreviewApiTests(APITestCase):
    databases = {"default", "store"}
    base = "/api/store/campaigns/"

    def setUp(self):
        cache.clear()

    def _create_campaign(self, *, slug, status, priority=0, start_delta=-1, end_delta=48, title=None):
        now = timezone.now()
        return Campaign.objects.create(
            name=f"ops-{slug}",
            slug=slug,
            title=title or slug,
            status=status,
            priority=priority,
            start_at=now + timedelta(hours=start_delta),
            end_at=now + timedelta(hours=end_delta),
        )

    def _unknown_404_body(self):
        unknown = self.client.get(f"{self.base}does-not-exist/")
        self.assertEqual(unknown.status_code, 404)
        return unknown.data

    def test_sign_unsign_roundtrip(self):
        draft = self._create_campaign(slug="draft-sign", status=Campaign.STATUS_DRAFT)
        token = sign_campaign_preview(draft)
        self.assertEqual(unsign_campaign_preview(token), (draft.pk, draft.slug))
        self.assertIsNone(unsign_campaign_preview(""))
        self.assertIsNone(unsign_campaign_preview(None))

    def test_draft_valid_token_200_is_preview(self):
        draft = self._create_campaign(slug="draft-ok", status=Campaign.STATUS_DRAFT, title="Draft title")
        token = sign_campaign_preview(draft)
        res = self.client.get(f"{self.base}{draft.slug}/", {"preview": token})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["slug"], "draft-ok")
        self.assertEqual(res.data["title"], "Draft title")
        self.assertTrue(res.data["is_preview"])

    def test_draft_no_token_404_identical(self):
        draft = self._create_campaign(slug="draft-hide", status=Campaign.STATUS_DRAFT)
        expected = self._unknown_404_body()
        missing = self.client.get(f"{self.base}{draft.slug}/")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.data, expected)

    def test_draft_empty_or_unsigned_preview_404(self):
        draft = self._create_campaign(slug="draft-bad", status=Campaign.STATUS_DRAFT)
        expected = self._unknown_404_body()
        for value in ("", "1"):
            res = self.client.get(f"{self.base}{draft.slug}/", {"preview": value})
            self.assertEqual(res.status_code, 404, value)
            self.assertEqual(res.data, expected)

    def test_draft_tampered_token_404(self):
        draft = self._create_campaign(slug="draft-tamper", status=Campaign.STATUS_DRAFT)
        token = sign_campaign_preview(draft)
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
        expected = self._unknown_404_body()
        res = self.client.get(f"{self.base}{draft.slug}/", {"preview": tampered})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data, expected)

    def test_expired_token_404(self):
        draft = self._create_campaign(slug="draft-expired", status=Campaign.STATUS_DRAFT)
        past = time.time() - 8000
        with patch("django.core.signing.time.time", return_value=past):
            token = sign_campaign_preview(draft)
        expected = self._unknown_404_body()
        res = self.client.get(f"{self.base}{draft.slug}/", {"preview": token})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data, expected)

    def test_token_slug_mismatch_404(self):
        draft_a = self._create_campaign(slug="draft-a", status=Campaign.STATUS_DRAFT)
        draft_b = self._create_campaign(slug="draft-b", status=Campaign.STATUS_DRAFT)
        token = sign_campaign_preview(draft_a)
        expected = self._unknown_404_body()
        res = self.client.get(f"{self.base}{draft_b.slug}/", {"preview": token})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data, expected)

    def test_live_no_token_no_is_preview(self):
        active = self._create_campaign(slug="live-show", status=Campaign.STATUS_ACTIVE)
        res = self.client.get(f"{self.base}{active.slug}/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertNotIn("is_preview", res.data)

    def test_live_with_token_no_is_preview(self):
        active = self._create_campaign(slug="live-token", status=Campaign.STATUS_ACTIVE)
        token = sign_campaign_preview(active)
        res = self.client.get(f"{self.base}{active.slug}/", {"preview": token})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertNotIn("is_preview", res.data)

    def test_out_of_window_preview_200(self):
        ended = self._create_campaign(
            slug="ended-preview",
            status=Campaign.STATUS_ACTIVE,
            start_delta=-48,
            end_delta=-1,
        )
        token = sign_campaign_preview(ended)
        res = self.client.get(f"{self.base}{ended.slug}/", {"preview": token})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["is_preview"])

    def test_list_still_hides_draft_after_preview(self):
        draft = self._create_campaign(slug="draft-list", status=Campaign.STATUS_DRAFT)
        active = self._create_campaign(slug="live-list", status=Campaign.STATUS_ACTIVE)
        token = sign_campaign_preview(draft)
        preview = self.client.get(f"{self.base}{draft.slug}/", {"preview": token})
        self.assertEqual(preview.status_code, 200)
        listing = self.client.get(self.base)
        self.assertEqual(listing.status_code, 200)
        slugs = {row["slug"] for row in listing.data}
        self.assertIn("live-list", slugs)
        self.assertNotIn("draft-list", slugs)

    def test_preview_does_not_seed_public_detail_cache(self):
        draft = self._create_campaign(slug="draft-cache", status=Campaign.STATUS_DRAFT)
        token = sign_campaign_preview(draft)
        preview = self.client.get(f"{self.base}{draft.slug}/", {"preview": token})
        self.assertEqual(preview.status_code, 200)
        self.assertIsNone(get_cached("detail", extra=draft.slug))
        public = self.client.get(f"{self.base}{draft.slug}/")
        self.assertEqual(public.status_code, 404)
