from django.db import IntegrityError
from rest_framework import viewsets, generics, status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from mainApp.models import TimeSlot
from mainApp.serializers import TimeSlotSerializer


class TimeSlotViewSet(viewsets.ViewSet, generics.CreateAPIView,
                      generics.DestroyAPIView, generics.RetrieveAPIView,
                      generics.UpdateAPIView, generics.ListAPIView):
    queryset = TimeSlot.objects.all().order_by('-id')
    serializer_class = TimeSlotSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            err_blob = str(serializer.errors).lower()
            if "unique" in err_blob:
                return Response(
                    data={"errMsg": "Time slot already taken for this schedule"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        schedule = serializer.validated_data.get('schedule')
        if schedule is not None and schedule.is_off:
            return Response(
                data={"errMsg": "Cannot create time slot on an off schedule"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_time = serializer.validated_data.get('start_time')
        end_time = serializer.validated_data.get('end_time')
        if start_time is not None and end_time is not None and start_time >= end_time:
            return Response(
                data={"errMsg": "start_time must be before end_time"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            schedule is not None
            and start_time is not None
            and end_time is not None
            and TimeSlot.objects.filter(
                schedule=schedule,
                start_time=start_time,
                end_time=end_time,
            ).exists()
        ):
            return Response(
                data={"errMsg": "Time slot already taken for this schedule"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self.perform_create(serializer)
        except IntegrityError:
            return Response(
                data={"errMsg": "Time slot already taken for this schedule"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
