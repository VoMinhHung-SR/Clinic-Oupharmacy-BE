from rest_framework.throttling import AnonRateThrottle

# 1) Rate limit: 5 requests per hour per IP
class ForgotPasswordThrottle(AnonRateThrottle):
    scope = "forgot_password"

# 2) Rate limit: 20 requests per hour per IP
class ResetPasswordThrottle(AnonRateThrottle):
    scope = "reset_password"
    