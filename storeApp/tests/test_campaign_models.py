"""Model constraints for Campaign / CampaignPlacement (P1-T1)."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from storeApp.models import Campaign, CampaignCategory, CampaignPlacement, CampaignProduct


class CampaignModelTests(TestCase):
    databases = {"default", "store"}

    def test_create_draft_campaign_and_placement(self):
        campaign = Campaign.objects.create(
            name="Ops Summer",
            slug="summer-2026",
            title="Summer Sale",
            status=Campaign.STATUS_DRAFT,
        )
        placement = CampaignPlacement.objects.create(
            campaign=campaign,
            slot=CampaignPlacement.SLOT_HOME_HERO,
            title="Hero",
            cta_url="/khuyen-mai/summer-2026",
        )
        self.assertEqual(campaign.version, 1)
        self.assertEqual(campaign.locale, "vi")
        self.assertTrue(placement.is_enabled)
        self.assertEqual(campaign.placements.count(), 1)

    def test_slug_unique(self):
        Campaign.objects.create(
            name="A",
            slug="dup-slug",
            title="A",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic(using="store"):
                Campaign.objects.create(
                    name="B",
                    slug="dup-slug",
                    title="B",
                )

    def test_end_at_must_be_after_start_at(self):
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic(using="store"):
                Campaign.objects.create(
                    name="Bad window",
                    slug="bad-window",
                    title="Bad",
                    start_at=now,
                    end_at=now - timedelta(hours=1),
                )

    def test_custom_permissions_declared(self):
        codenames = {p[0] for p in Campaign._meta.permissions}
        self.assertIn("campaign_view", codenames)
        self.assertIn("campaign_manage", codenames)

    def test_campaign_product_and_category_unique(self):
        campaign = Campaign.objects.create(
            name="Scope",
            slug="scope-unique",
            title="Scope",
        )
        CampaignProduct.objects.create(campaign=campaign, product_mid="MID001")
        CampaignCategory.objects.create(campaign=campaign, category_slug="duoc-my-pham")
        with self.assertRaises(IntegrityError):
            with transaction.atomic(using="store"):
                CampaignProduct.objects.create(campaign=campaign, product_mid="MID001")
        with self.assertRaises(IntegrityError):
            with transaction.atomic(using="store"):
                CampaignCategory.objects.create(campaign=campaign, category_slug="duoc-my-pham")
