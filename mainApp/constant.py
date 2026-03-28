MAX_EXAMINATION_PER_DAY = 30
SERVICE_FEE_PER_PRESCRIBING = 20000

ROLE_DOCTOR = 'ROLE_DOCTOR'
ROLE_NURSE = 'ROLE_NURSE'
ROLE_USER = 'ROLE_USER'

CLOUDINARY_DEFAULT_AVATAR = 'OUPharmacy/logo_oupharmacy_kz2yzd.png'
ERR_NULL_AVATAR = 'image/upload/null'

# Limit configurations (models / list APIs)
LIMIT_USER_LOCATION = 10  # max locations per user (e.g. saved addresses)
LIMIT_LOCATION_LIST = 100  # max items in common-locations list API
DEFAULT_LIST_LIMIT = 20  # default pagination/list size for mainApp list endpoints
MAX_LIST_LIMIT = 100  # cap for request query param limit