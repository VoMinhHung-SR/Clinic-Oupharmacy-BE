from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from storeApp.services.cabinet_prescription_seed import list_prescription_lines_for_user


class CabinetPrescriptionLinesView(APIView):
    """Owner-scoped prescription lines for seeding a personal medicine cabinet."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = request.query_params.get("limit")
        try:
            limit_n = int(limit) if limit is not None else 100
        except (TypeError, ValueError):
            limit_n = 100
        rows = list_prescription_lines_for_user(request.user.id, limit=min(max(limit_n, 1), 200))
        return Response(rows)
