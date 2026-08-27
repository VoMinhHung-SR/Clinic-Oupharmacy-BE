"""Product pricing helpers (D-PRC Option 1)."""

from decimal import Decimal

from django.test import TestCase

from storeApp.services.product_pricing import (
    discount_percent_from_prices,
    list_price_for_promotion,
    sale_price_from_list,
    tier_promo_prices,
)


class ProductPricingTests(TestCase):
    databases = {"default", "store"}

    def test_sale_price_from_list_lowers_price(self):
        sale = sale_price_from_list(Decimal("606000"), 30)
        self.assertEqual(sale, Decimal("424200"))

    def test_discount_percent_from_list_and_sale(self):
        pct = discount_percent_from_prices(Decimal("424200"), Decimal("606000"))
        self.assertEqual(pct, 30)

    def test_tier_promo_prices(self):
        class Unit:
            price_value = Decimal("100000")
            compare_at_price = None

        promo = tier_promo_prices(Unit(), 30)
        self.assertIsNotNone(promo)
        assert promo is not None
        self.assertEqual(promo.list_price, Decimal("100000"))
        self.assertEqual(promo.sale_price, Decimal("70000"))
        self.assertEqual(promo.discount_percent, 30)

    def test_list_price_prefers_existing_compare_at(self):
        class Unit:
            price_value = Decimal("100000")
            compare_at_price = Decimal("150000")

        self.assertEqual(list_price_for_promotion(Unit()), Decimal("150000"))
        promo = tier_promo_prices(Unit(), 30)
        assert promo is not None
        self.assertEqual(promo.list_price, Decimal("150000"))
        self.assertEqual(promo.sale_price, Decimal("105000"))
