"""Two-tier admin: system superuser (full Jazzmin) vs business admin (clinic FE + Campaign-scoped Jazzmin)."""


def is_system_superadmin(user):
    """Full Jazzmin (all models) + system ops. is_superuser only."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_superuser", False)
    )


def is_business_admin(user):
    """Clinic FE ops + store/clinic business APIs + Jazzmin login (D-18)."""
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return bool(getattr(user, "is_admin", False) or getattr(user, "is_superuser", False))
