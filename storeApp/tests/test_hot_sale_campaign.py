"""Hot-sale campaign: real tier promos + ProductUnitPromotion revert."""

from decimal import Decimal

from django.test import TestCase

from storeApp.models import Campaign, CampaignProduct, Category, Product, ProductUnitPromotion, ProductVariant, ProductVariantUnit
from storeApp.services.hot_sale_campaign import (
    HOT_SALE_CAMPAIGN_SLUG,
    fetch_popular_variants_for_hot_sale,
    plan_hot_sale_rows,
    revert_hot_sale_promotions,
    tier_percent_for_index,
    upsert_hot_sale_campaign,
)
from storeApp.services.product_pricing import sale_price_from_list


class HotSaleCampaignServiceTests(TestCase):
    databases = {"default", "store"}

    def setUp(self):
        self.category = Category.objects.create(name="Test", slug="test-hot-sale")

    def _create_variant(self, *, mid: str, name: str, price: str, ranking: int):
        product = Product.objects.create(
            name=name,
            slug=f"slug-{mid.lower()}",
            mid=mid,
            category=self.category,
        )
        variant = ProductVariant.objects.create(
            product=product,
            packing="Hộp",
            is_published=True,
            in_stock=50,
            product_ranking=ranking,
        )
        ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Hộp",
            quantity_in_base=1,
            price_value=Decimal(price),
            is_default=True,
            is_published=True,
        )
        return variant

    def test_sale_price_from_list_606k_tier_30(self):
        sale = sale_price_from_list(Decimal("606000"), 30)
        self.assertEqual(sale, Decimal("424200"))

    def test_tier_cycles_30_25_20(self):
        self.assertEqual(tier_percent_for_index(0), 30)
        self.assertEqual(tier_percent_for_index(1), 25)
        self.assertEqual(tier_percent_for_index(2), 20)
        self.assertEqual(tier_percent_for_index(3), 30)

    def test_apply_hot_sale_lowers_price_and_sets_compare_at(self):
        self._create_variant(mid="MID-A", name="Alpha", price="606000", ranking=100)
        self._create_variant(mid="MID-B", name="Beta", price="200000", ranking=90)
        self._create_variant(mid="MID-C", name="Gamma", price="300000", ranking=80)

        variants = fetch_popular_variants_for_hot_sale("store", fetch_size=10)
        plans = plan_hot_sale_rows(variants, page_size=3)
        self.assertEqual(len(plans), 3)

        top = plans[0]
        self.assertEqual(top.product_mid, "MID-A")
        self.assertEqual(top.promo.list_price, Decimal("606000"))
        self.assertEqual(top.promo.sale_price, Decimal("424200"))
        self.assertEqual(top.promo.discount_percent, 30)

        campaign = upsert_hot_sale_campaign(plans, using="store")
        assert campaign is not None
        unit = ProductVariantUnit.objects.get(pk=top.unit.id)
        self.assertEqual(unit.price_value, Decimal("424200"))
        self.assertEqual(unit.compare_at_price, Decimal("606000"))

        promo = ProductUnitPromotion.objects.get(campaign=campaign, product_variant_unit=unit)
        self.assertTrue(promo.is_active)
        self.assertEqual(promo.previous_price_value, Decimal("606000"))

        mids = list(
            CampaignProduct.objects.filter(campaign=campaign)
            .order_by("sort_order")
            .values_list("product_mid", flat=True)
        )
        self.assertEqual(mids[0], "MID-A")

    def test_revert_restores_previous_prices(self):
        variant = self._create_variant(mid="MID-R", name="Revert", price="100000", ranking=99)
        unit = variant.units.get(is_default=True)
        unit.compare_at_price = Decimal("150000")
        unit.save(update_fields=["compare_at_price"])

        plans = plan_hot_sale_rows([variant], page_size=1)
        campaign = upsert_hot_sale_campaign(plans, using="store")
        assert campaign is not None

        unit.refresh_from_db()
        self.assertEqual(unit.price_value, Decimal("105000"))
        self.assertEqual(unit.compare_at_price, Decimal("150000"))

        reverted = revert_hot_sale_promotions(using="store")
        self.assertEqual(reverted, 1)
        unit.refresh_from_db()
        self.assertEqual(unit.price_value, Decimal("100000"))
        self.assertEqual(unit.compare_at_price, Decimal("150000"))

    def test_checkout_subtotal_uses_lowered_sale_price(self):
        variant = self._create_variant(mid="MID-CO", name="Checkout", price="100000", ranking=100)
        plans = plan_hot_sale_rows([variant], page_size=1)
        upsert_hot_sale_campaign(plans, using="store")

        unit = variant.units.get(is_default=True)
        unit.refresh_from_db()
        line_total = unit.price_value * 2
        self.assertEqual(line_total, Decimal("140000"))

    def test_hot_sale_applies_tier_to_all_published_units(self):
        product = Product.objects.create(
            name="Multi unit",
            slug="multi-unit-hot",
            mid="MID-MU",
            category=self.category,
        )
        variant = ProductVariant.objects.create(
            product=product,
            packing="Thùng",
            is_published=True,
            in_stock=50,
            product_ranking=200,
        )
        thung = ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Thùng",
            quantity_in_base=12,
            price_value=Decimal("606000"),
            is_default=True,
            is_published=True,
        )
        chai = ProductVariantUnit.objects.create(
            variant=variant,
            unit_name="Chai",
            quantity_in_base=1,
            price_value=Decimal("50500"),
            is_default=False,
            is_published=True,
        )

        plans = plan_hot_sale_rows([variant], page_size=1)
        upsert_hot_sale_campaign(plans, using="store")

        thung.refresh_from_db()
        chai.refresh_from_db()
        self.assertEqual(thung.price_value, Decimal("424200"))
        self.assertEqual(thung.compare_at_price, Decimal("606000"))
        self.assertEqual(chai.price_value, Decimal("35350"))
        self.assertEqual(chai.compare_at_price, Decimal("50500"))
        self.assertEqual(
            ProductUnitPromotion.objects.filter(product_variant_unit__variant=variant, is_active=True).count(),
            2,
        )
