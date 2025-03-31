import datetime
import math
import pytz
from django.utils import timezone

from rest_framework import viewsets, generics, status, filters, permissions
from rest_framework.response import Response
from django.core.mail import EmailMessage
from mainApp.constant import MAX_EXAMINATION_PER_DAY
from mainApp.filters import ExaminationFilter
from mainApp.models import  TimeSlot, Examination, Patient, Diagnosis
from mainApp.paginator import ExaminationPaginator
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

from mainApp.serializers import DiagnosisSerializer
from mainApp.serializers import ExaminationSerializer, ExaminationsPairSerializer
# Create your views here.
wageBooking = 20000

class ExaminationViewSet(viewsets.ViewSet, generics.ListAPIView,
                         generics.RetrieveAPIView,
                         generics.DestroyAPIView, generics.UpdateAPIView):
    queryset = Examination.objects.filter(active=True).order_by('-created_date')
    serializer_class = ExaminationSerializer
    pagination_class = ExaminationPaginator
    ordering_fields = '__all__'
    filterset_class = ExaminationFilter
    filter_backends = [filters.OrderingFilter, DjangoFilterBackend]
    permissions = [permissions.AllowAny()]

    def create(self, request):
        user = request.user
        if user:
            try:
                patient = Patient.objects.get(pk=request.data.get('patient'))
                description = request.data.get('description')
                created_date = request.data.get('created_date')
                time_slot = TimeSlot.objects.get(pk=request.data.get('time_slot'))
            except:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            if patient:
                current_day = timezone.now()
                max_examinations = MAX_EXAMINATION_PER_DAY
                today_utc = current_day.replace(hour=0, minute=0, second=0).astimezone(pytz.utc)
                tomorrow_utc = current_day.replace(hour=23, minute=59, second=59).astimezone(pytz.utc)

                if Examination.objects.filter(created_date__range=(today_utc, tomorrow_utc)).count() > max_examinations:
                    return Response(data={"errMsg": "Maximum number of examinations reached"},
                                    status=status.HTTP_400_BAD_REQUEST)
                try:
                    e = Examination.objects.create(description=description, patient=patient,
                                                   user=user, time_slot=time_slot)
                    if created_date:
                        e.created_date = created_date
                    e.save()
                    return Response(ExaminationSerializer(e, context={'request': request}).data,
                                    status=status.HTTP_201_CREATED)
                except:
                    return Response(data={"errMsg": "Error occurred while creating examination"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            else:
                return Response(data={"errMgs": "Patient doesn't exist"},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data={"errMgs": "User not found"},
                            status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk=None):
        user = request.user
        if user:
            try:
                patient = Patient.objects.get(pk=request.data.get('patient'))
                description = request.data.get('description')
                created_date = request.data.get('created_date')
                time_slot = TimeSlot.objects.get(pk=request.data.get('time_slot'))
            except:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            if patient:
                try:
                    e = self.get_object(pk)
                    if created_date:
                        e.created_date = created_date
                    e.description = description
                    e.patient = patient
                    e.user = user
                    e.time_slot = time_slot
                    e.save()
                    return Response(ExaminationSerializer(e, context={'request': request}).data,
                                    status=status.HTTP_200_OK)
                except:
                    return Response(data={"errMsg": "Error occurred while updating examination"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response(data={"errMsg": "Patient doesn't exist"},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(data={"errMsg": "User not found"},
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=True, url_path='send_mail')
    def send_email(self, request, pk):
        examination = self.get_object()
        error_msg = None
        if examination:
            if not examination.mail_status:
                user = examination.user
                patient = examination.patient
                if user and patient:
                    try:
                        current_date = datetime.date.today().strftime('%d-%m-%Y')
                        subject = "Thư xác nhận lịch đăng ký khám"
                        to_user = user.email
                        content = """Xin chào {0},
Phiếu đặt lịch của bạn đã được xác nhận vào ngày {6}, bạn có một lịch hẹn khám vơi OUPharmacy vào ngày {4:%d-%m-%Y}!!!

Chi tiết lịch đặt khám của {0}:
(+)  Mã đặt lịch: {1}
(+)  Họ tên bệnh nhân: {2}
(+)  Mô tả: {3}
(+)  Ngày đăng ký:{4:%d-%m-%Y}
=====================
(-)  Phí khám của bạn là: {5:,.0f} VND

Địa điểm: 371 Nguyễn Kiệm, Phường 3, Gò Vấp, Thành phố Hồ Chí Minh


Vui lòng xem kỹ lại thông tin thời gian và địa diểm, để hoàn tất thủ tục khám.
OUPharmacy xin chúc bạn một ngày tốt lành và thật nhiều sức khỏe, xin chân thành cả́m ơn.""".format(
                            user.first_name + " " + user.last_name,
                            examination.pk,
                            patient.first_name + " " + patient.last_name,
                            examination.description,
                            examination.created_date,
                            examination.wage,
                            current_date)
                        if content and subject and to_user:
                            send_email = EmailMessage(subject, content, to=[to_user])
                            send_email.send()
                        else:
                            error_msg = "Send mail failed !!!"
                    except:
                        error_msg = 'Email content error!!!'
                else:
                    error_msg = 'User and patient not found !!!'
            else:
                error_msg = 'Email was sent already!!!'
        if not error_msg:
            examination.mail_status = True
            examination.save()
            return Response(data={
                'status': 'Send mail successfully',
                'to': to_user,
                'subject': subject,
                'content': content
            }, status=status.HTTP_200_OK)
        return Response(data={'errMgs': error_msg},
                        status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post'], detail=True, url_path='send_email_remind1')
    def send_email_remind1(self, request, pk):
        examination = self.get_object()
        if not examination:
            return Response(data={'errMsg': 'Examination not found'},
                            status=status.HTTP_404_NOT_FOUND)
        user = examination.user
        patient = examination.patient
        doctor_availability = examination.doctor_availability
        if not user or not patient:
            return Response(data={'errMsg': 'User or patient not found'},
                            status=status.HTTP_400_BAD_REQUEST)
        seconds = request.data.get('seconds') / 60
        minutes = math.ceil(int(seconds))
        subject = "Thông báo: phiếu đăng ký khám của bạn sắp bắt đầu"
        to_user = user.email
        content = f"""Xin chào {user.first_name} {user.last_name},
Phiếu khám của bạn sẽ bắt đầu sau: {minutes} phút.

Bệnh nhân {patient.first_name} {patient.last_name} của bạn có lịch khám với chúng tôi vào ngày {doctor_availability.day:%d-%m-%Y}.

Chi tiết lịch đặt khám của bạn:
(+)  Mã đặt lịch: {examination.pk}
(+)  Họ tên bệnh nhân: {patient.first_name} {patient.last_name}
(+)  Mô tả: {examination.description}
(+)  Ngày đăng ký: {doctor_availability.day:%d-%m-%Y}
=====================
(-)  Phí khám của bạn là: {examination.wage:,.0f} VND

Địa điểm: 371 Nguyễn Kiệm, Phường 3, Gò Vấp, Thành phố Hồ Chí Minh

Vui lòng xem kỹ lại thông tin thời gian và địa điểm, để hoàn tất thủ tục khám.
OUPharmacy xin chúc bạn một ngày tốt lành và thật nhiều sức khỏe, xin chân thành cả́m ơn."""
        try:
            send_email = EmailMessage(subject, content, to=[to_user])
            send_email.send()
        except:
            return Response(data={'errMsg': 'Failed to send email'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        examination.mail_status = True
        examination.save()
        return Response(data={
            'status': 'Send mail successfully',
            'to': to_user,
            'subject': subject,
            'content': content
        }, status=status.HTTP_200_OK)

    @action(methods=['get'], detail=True, url_path='get-diagnosis')
    def get_diagnosis(self, request, pk):
        try:
            diagnosis = Diagnosis.objects.filter(examination_id=pk)
        except Exception as ex:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"errMgs": "prescription not found"})
        if diagnosis:
            return Response(DiagnosisSerializer(diagnosis.first(), context={'request': request}).data,
                            status=status.HTTP_200_OK)
        return Response(data={}, status=status.HTTP_200_OK)

    @action(methods=['post'], detail=False, url_path='get-total-exams')
    def get_total_exam_per_day(self, request):
        date_str = request.data.get('date')
        try:
            date = datetime.datetime.strptime(date_str,
                                              '%Y-%m-%d').date() if date_str else datetime.datetime.now().date()
            start_of_day = datetime.datetime.combine(date, datetime.time.min).astimezone(pytz.utc)
            end_of_day = datetime.datetime.combine(date, datetime.time.max).astimezone(pytz.utc)
            examinations = Examination.objects.filter(created_date__range=(start_of_day, end_of_day))
            total_exams = examinations.count()
            return Response(
                data={
                    "totalExams": total_exams,
                    "dateStr": date,
                    "examinations": ExaminationSerializer(examinations, context={'request': request}, many=True).data
                },
                status=status.HTTP_200_OK,
            )
        except ValueError:
            return Response(
                data={"errMsg": "Invalid date format. Use 'YYYY-MM-DD'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            return Response(
                data={"errMsg": "An error occurred while fetching examinations."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(methods=['get'], detail=False, url_path='get-list-exam-today')
    def get_list_exam_today(self, request):
        try:
            now = datetime.datetime.now()
            today = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
            tomorrow = now.replace(hour=23, minute=59, second=59).astimezone(pytz.utc)
            examinations = Examination.objects.filter(created_date__range=(today,
                                                                           tomorrow)).order_by('created_date').all()
        except Exception as error:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            data={"errMgs": "Can't get Examinations"})
        if examinations:
            return Response(data=ExaminationsPairSerializer(examinations, context={'request': request}, many=True).data,
                            status=status.HTTP_200_OK)
        return Response(data=[],
                        status=status.HTTP_200_OK)
