"""Two-tier admin: Jazzmin superuser vs business is_admin."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from mainApp.admin import admin_site
from mainApp.authz import is_business_admin, is_system_superadmin
from mainApp.permissions import IsBusinessAdmin


class AuthzTierTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            email="super@example.com",
            password="test-pass-123",
        )
        self.biz = User.objects.create_user(
            email="biz-admin@example.com",
            password="test-pass-123",
            is_admin=True,
            is_staff=False,
            is_superuser=False,
        )
        self.staff_only = User.objects.create_user(
            email="staff-only@example.com",
            password="test-pass-123",
            is_admin=False,
            is_staff=True,
            is_superuser=False,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="test-pass-123",
        )

    def test_flags(self):
        self.assertTrue(is_system_superadmin(self.superuser))
        self.assertTrue(is_business_admin(self.superuser))
        self.assertFalse(is_system_superadmin(self.biz))
        self.assertTrue(is_business_admin(self.biz))
        self.assertFalse(is_system_superadmin(self.staff_only))
        self.assertFalse(is_business_admin(self.staff_only))
        self.assertFalse(is_business_admin(self.customer))

    def test_jazzmin_superuser_or_business_admin(self):
        req = self.factory.get("/admin/")
        req.user = self.superuser
        self.assertTrue(admin_site.has_permission(req))
        req.user = self.biz
        self.assertTrue(admin_site.has_permission(req))
        req.user = self.staff_only
        self.assertFalse(admin_site.has_permission(req))
        req.user = self.customer
        self.assertFalse(admin_site.has_permission(req))

    def test_campaign_admin_scoped_for_is_admin(self):
        from storeApp.admin import CampaignAdmin
        from storeApp.models import Campaign
        from storeApp.admin import BrandAdmin
        from storeApp.models import Brand

        req = self.factory.get("/admin/")
        req.user = self.biz
        campaign_ma = CampaignAdmin(Campaign, admin_site)
        self.assertTrue(campaign_ma.has_module_permission(req))
        self.assertTrue(campaign_ma.has_add_permission(req))
        brand_ma = BrandAdmin(Brand, admin_site)
        self.assertFalse(brand_ma.has_module_permission(req))

    def test_has_perm_not_granted_by_is_admin(self):
        self.assertTrue(self.superuser.has_perm("storeApp.campaign_view"))
        self.assertFalse(self.biz.has_perm("storeApp.campaign_view"))
        self.assertFalse(self.staff_only.has_perm("storeApp.campaign_view"))

    def test_drf_business_admin(self):
        perm = IsBusinessAdmin()
        req = self.factory.get("/")
        req.user = self.biz
        self.assertTrue(perm.has_permission(req, None))
        req.user = self.staff_only
        self.assertFalse(perm.has_permission(req, None))
        req.user = self.customer
        self.assertFalse(perm.has_permission(req, None))
