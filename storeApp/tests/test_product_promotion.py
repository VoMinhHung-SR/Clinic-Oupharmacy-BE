"""Unified catalog promo lifecycle — auto revert (P1b / D-PRC)."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from storeApp.models import Campaign, Category, Product, ProductUnitPromotion, ProductVariant, ProductVariantUnit
from storeApp.services.campaign_service import run_campaign_scheduler
from storeApp.services.hot_sale_campaign import (
    plan_hot_sale_rows,
    revert_hot_sale_promotions,
    upsert_hot_sale_campaign,
)
from storeApp.services.product_pricing import tier_promo_prices
from storeApp.services.product_promotion import (
    apply_unit_promotion,
    revert_expired_unit_promotions,
    revert_unit_promotion,
)


class ProductPromotionLifecycleTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.create(name="Promo", slug="promo-lifecycle")
        self.now = timezone.now()

    def _create_unit(self, *, mid: str, price: str, ranking: int = 50):
        product = Product.objects.create(
            name=f"Product {mid}",
            slug=f"slug-{mid.lower()}",
            mid=mid,
            category=self.category,
        )
        variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            is_published=True,
            in_stock=10,
            product_ranking=ranking,
        )
        unit = ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal(price),
            is_default=True,
            is_published=True,
        )
        return unit

    def _campaign(self, *, slug: str, priority: int = 100, end_at=None, status=Campaign.STATUS_ACTIVE):
        return Campaign.objects.create(
            name=slug,
            slug=slug,
            title=slug,
            status=status,
            priority=priority,
            start_at=self.now - timedelta(days=1),
            end_at=end_at or (self.now + timedelta(days=7)),
        )

    def test_revert_expired_by_promo_ends_at(self):
        unit = self._create_unit(mid="EXP-1", price="100000")
        campaign = self._campaign(slug="exp-promo-ends")
        promo_prices = tier_promo_prices(unit, 20)
        assert promo_prices is not None

        apply_unit_promotion(
            campaign=campaign,
            unit=unit,
            promo=promo_prices,
            tier_percent=20,
            ends_at=self.now - timedelta(minutes=1),
            using="store",
        )
        unit.refresh_from_db()
        self.assertEqual(unit.price_value, promo_prices.sale_price)

        stats = revert_expired_unit_promotions(now=self.now, using="store")
        self.assertEqual(stats["reverted"], 1)

        unit.refresh_from_db()
        self.assertEqual(unit.price_value, Decimal("100000"))
        self.assertFalse(
            ProductUnitPromotion.objects.filter(campaign=campaign, is_active=True).exists()
        )

    def test_scheduler_reverts_when_campaign_ends(self):
        unit = self._create_unit(mid="EXP-2", price="200000")
        campaign = self._campaign(
            slug="exp-campaign-end",
            end_at=self.now - timedelta(minutes=1),
            status=Campaign.STATUS_ACTIVE,
        )
        promo_prices = tier_promo_prices(unit, 25)
        assert promo_prices is not None

        apply_unit_promotion(
            campaign=campaign,
            unit=unit,
            promo=promo_prices,
            tier_percent=25,
            ends_at=self.now + timedelta(days=1),
            using="store",
        )
        unit.refresh_from_db()
        self.assertEqual(unit.price_value, promo_prices.sale_price)

        stats = run_campaign_scheduler(now=self.now)
        campaign.refresh_from_db()
        unit.refresh_from_db()

        self.assertEqual(campaign.status, Campaign.STATUS_ENDED)
        self.assertGreaterEqual(stats["promo_reverted"], 1)
        self.assertEqual(unit.price_value, Decimal("200000"))

    def test_overlap_keeps_higher_priority_promo_on_partial_revert(self):
        unit = self._create_unit(mid="OVL-1", price="100000")
        low = self._campaign(slug="low-priority", priority=10)
        high = self._campaign(slug="high-priority", priority=200)

        low_prices = tier_promo_prices(unit, 10)
        high_prices = tier_promo_prices(unit, 30)
        assert low_prices is not None and high_prices is not None

        apply_unit_promotion(
            campaign=low,
            unit=unit,
            promo=low_prices,
            tier_percent=10,
            using="store",
        )
        apply_unit_promotion(
            campaign=high,
            unit=unit,
            promo=high_prices,
            tier_percent=30,
            using="store",
        )
        unit.refresh_from_db()
        self.assertEqual(unit.price_value, high_prices.sale_price)

        low_promo = ProductUnitPromotion.objects.get(campaign=low, product_variant_unit=unit)
        revert_unit_promotion(low_promo, using="store")

        unit.refresh_from_db()
        self.assertEqual(unit.price_value, high_prices.sale_price)
        self.assertTrue(
            ProductUnitPromotion.objects.get(campaign=high, product_variant_unit=unit).is_active
        )

    def test_hot_sale_manual_revert_still_works(self):
        unit = self._create_unit(mid="HS-1", price="100000", ranking=99)
        plans = plan_hot_sale_rows([unit.variant], page_size=1)
        upsert_hot_sale_campaign(plans, using="store", start_at=self.now, end_at=self.now + timedelta(days=30))

        unit.refresh_from_db()
        self.assertLess(unit.price_value, Decimal("100000"))

        reverted = revert_hot_sale_promotions(using="store")
        self.assertEqual(reverted, 1)
        unit.refresh_from_db()
        self.assertEqual(unit.price_value, Decimal("100000"))

    def test_revert_expired_idempotent(self):
        unit = self._create_unit(mid="IDEM-1", price="50000")
        campaign = self._campaign(slug="idem-promo")
        promo_prices = tier_promo_prices(unit, 20)
        assert promo_prices is not None

        apply_unit_promotion(
            campaign=campaign,
            unit=unit,
            promo=promo_prices,
            tier_percent=20,
            ends_at=self.now - timedelta(hours=1),
            using="store",
        )

        first = revert_expired_unit_promotions(now=self.now, using="store")
        second = revert_expired_unit_promotions(now=self.now, using="store")
        self.assertEqual(first["reverted"], 1)
        self.assertEqual(second["reverted"], 0)

    def test_cms_source_constant_available(self):
        self.assertEqual(ProductUnitPromotion.SOURCE_CMS, "cms")
        self.assertEqual(ProductUnitPromotion.SOURCE_FLASH_SALE, "flash_sale")
