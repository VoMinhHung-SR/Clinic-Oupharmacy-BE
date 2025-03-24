import datetime
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from mainApp.models import DoctorSchedule, TimeSlot, User
from mainApp.serializers import DoctorScheduleSerializer, TimeSlotSerializer
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.decorators import action
class DoctorScheduleViewSet(viewsets.ViewSet, generics.CreateAPIView,
                  generics.DestroyAPIView, generics.RetrieveAPIView,
                  generics.UpdateAPIView, generics.ListAPIView):
    queryset = DoctorSchedule.objects.all().order_by('-date')
    serializer_class = DoctorScheduleSerializer
    parser_classes = [JSONParser, MultiPartParser]

    @action(methods=['post'], detail=False, url_path='schedule')
    def get_schedule_by_date(self, request):
        date_str = request.data.get('date')
        doctor_id = request.data.get('doctor')
        try:
            if date_str and doctor_id:
                date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                doctor_data = DoctorSchedule.objects.filter(doctor=doctor_id, date=date).all()
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST,
                                data={"errMsg": "Can't get data, doctor or date is false"})

        except Exception as error:
            print(error)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"errMsg": "Cant get data doctor or date is false"})

        if doctor_data:
            if doctor_data:
                doctor_data_serialized = DoctorScheduleSerializer(doctor_data, context={'request': request},
                                                                  many=True).data
                for doctor in doctor_data_serialized:
                    time_slots = TimeSlot.objects.filter(schedule=doctor['id']).all()
                    doctor['time_slots'] = TimeSlotSerializer(time_slots, context={'request': request}, many=True).data

                return Response(
                    data=doctor_data_serialized,
                    status=status.HTTP_200_OK
                )
        return Response(data=[], status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False, url_path='create-weekly-schedule')
    def create_weekly_schedule(self, request):
        doctor_id = request.data.get('doctorID')
        weekly_schedule = request.data.get('weekly_schedule')

        if not doctor_id or not weekly_schedule:
            return Response(status=status.HTTP_400_BAD_REQUEST,
                            data={"errMsg": "Missing required parameters"})

        try:
            for date_str, sessions in weekly_schedule.items():
                current_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                for session_name, session_info in sessions.items():
                    session = session_info.get('session')
                    is_off = session_info.get('is_off', False)
                    if is_off:
                        continue

                    DoctorSchedule.objects.create(
                        doctor_id=doctor_id,
                        date=current_date,
                        session=session,
                        is_off=is_off
                    )

            return Response(status=status.HTTP_201_CREATED, data={"msg": "Weekly schedule created successfully"})
        except Exception as error:
            print(error)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"errMsg": "Error creating weekly schedule"})

    @action(methods=['get'], detail=False, url_path='doctor-stats')
    def get_doctor_stats(self, request):
        week_str = request.query_params.get('week')
        if not week_str:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"errMsg": "Missing required parameter: week"})

        try:
            week_start = datetime.datetime.strptime(week_str + '-1', '%G-W%V-%u').date()
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"errMsg": "Invalid week format. Use YYYY-Www"})

        try:
            doctors = User.objects.filter(role__name='ROLE_DOCTOR').all()
            doctor_stats = []
            total_counts = [0] * 7

            for doctor in doctors:
                schedule_counts = [0] * 7
                for i in range(7):
                    day = week_start + datetime.timedelta(days=i)
                    time_slot_count = TimeSlot.objects.filter(schedule__doctor=doctor, schedule__date=day).count()
                    schedule_counts[i] = time_slot_count
                    total_counts[i] += time_slot_count

                doctor_stats.append({
                    'label': f"{doctor.first_name} {doctor.last_name}",
                    'data': schedule_counts
                })

            doctor_stats.append({
                'label': 'Total Appointments',
                'data': total_counts
            })

            return Response(data=doctor_stats, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"errMsg": "Doctor or schedule not found"})

        except ValidationError as ve:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"errMsg": str(ve)})

        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"errMsg": "Internal server error"})
        
    @action(methods=['get'], detail=False, url_path='check-weekly-schedule')
    def check_weekly_schedule(self, request):
        week_str = request.query_params.get('week')
        doctor_id = request.query_params.get('doctor_id')
        
        if not week_str:
            return Response(status=status.HTTP_400_BAD_REQUEST, 
                          data={"errMsg": "Missing required parameter: week"})

        try:
            # Parse the week string (e.g., "2025-W11")
            week_start = datetime.datetime.strptime(week_str + '-1', '%G-W%V-%u').date()
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST, 
                          data={"errMsg": "Invalid week format. Use YYYY-Www"})

        try:
            # Filter doctors based on doctor_id if provided
            if doctor_id:
                doctors = User.objects.filter(role__name='ROLE_DOCTOR', id=doctor_id).all()
            else:
                doctors = User.objects.filter(role__name='ROLE_DOCTOR').all()

            weekly_schedule = {}

            for doctor in doctors:
                doctor_schedule = {}
                for i in range(7):
                    current_date = week_start + datetime.timedelta(days=i)
                    date_str = current_date.strftime('%Y-%m-%d')
                    
                    schedules = DoctorSchedule.objects.filter(
                        doctor=doctor,
                        date=current_date
                    ).all()

                    day_schedule = {}
                    for schedule in schedules:
                        time_slots = TimeSlot.objects.filter(schedule=schedule).all()
                        day_schedule[schedule.session] = {
                            'session': schedule.session,
                            'is_off': schedule.is_off,
                            'time_slots': TimeSlotSerializer(time_slots, many=True).data
                        }

                    doctor_schedule[date_str] = day_schedule

                weekly_schedule[doctor.email] = doctor_schedule

            return Response(data=weekly_schedule, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, 
                          data={"errMsg": "Doctor not found"})

        except ValidationError as ve:
            return Response(status=status.HTTP_400_BAD_REQUEST, 
                          data={"errMsg": str(ve)})

        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          data={"errMsg": "Internal server error"})

    @action(methods=['put'], detail=False, url_path='update-weekly-schedule')
    def update_weekly_schedule(self, request):
        doctor_id = request.data.get('doctorID')
        weekly_schedule = request.data.get('weekly_schedule')
        week_str = request.query_params.get('week')

        if not all([doctor_id, weekly_schedule, week_str]):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Missing required parameters"}
            )

        try:
            # Parse week string to get date range
            week_start = datetime.datetime.strptime(week_str + '-1', '%G-W%V-%u').date()
            week_end = week_start + datetime.timedelta(days=6)

            # Xóa tất cả lịch cũ trong tuần được chọn
            DoctorSchedule.objects.filter(
                doctor_id=doctor_id,
                date__range=[week_start, week_end]
            ).delete()

            # Tạo lịch mới
            new_schedules = []
            for date_str, sessions in weekly_schedule.items():
                current_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                
                for session_name, session_info in sessions.items():
                    session = session_info.get('session')
                    is_off = session_info.get('is_off', False)
                    
                    # Chỉ tạo lịch cho các buổi không off
                    if not is_off:
                        schedule = DoctorSchedule.objects.create(
                            doctor_id=doctor_id,
                            date=current_date,
                            session=session,
                            is_off=is_off
                        )
                        new_schedules.append(schedule)

            return Response(
                status=status.HTTP_200_OK,
                data={
                    "msg": "Weekly schedule updated successfully",
                    "updated_schedules": len(new_schedules)
                }
            )

        except ValueError:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"errMsg": "Invalid week format"}
            )
        except Exception as error:
            print(error)
            return Response(
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                data={"errMsg": "Error updating weekly schedule"}
            )