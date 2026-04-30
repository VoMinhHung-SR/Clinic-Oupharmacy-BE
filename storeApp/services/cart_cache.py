class CartCacheGateway:
    """Cache abstraction for cart and voucher derived data."""

    def get_cart_summary(self, *, cart_id):
        raise NotImplementedError

    def set_cart_summary(self, *, cart_id, summary, ttl_seconds=None):
        raise NotImplementedError

    def invalidate_cart_summary(self, *, cart_id):
        raise NotImplementedError

    def invalidate_user_active_cart(self, *, user_id):
        raise NotImplementedError

    def invalidate_voucher_light(self, *, voucher_code):
        raise NotImplementedError


class NoopCartCacheGateway(CartCacheGateway):
    def get_cart_summary(self, *, cart_id):
        return None

    def set_cart_summary(self, *, cart_id, summary, ttl_seconds=None):
        return None

    def invalidate_cart_summary(self, *, cart_id):
        return None

    def invalidate_user_active_cart(self, *, user_id):
        return None

    def invalidate_voucher_light(self, *, voucher_code):
        return None


_gateway = NoopCartCacheGateway()


def get_cart_cache_gateway():
    return _gateway

