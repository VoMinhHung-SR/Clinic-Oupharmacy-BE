import json
import os
from datetime import timedelta, datetime, time

import pytz
from django.core.mail import EmailMessage
from django.db.models import F
from django.utils import timezone

from celery import shared_task
from firebase_admin import firestore

from .models import Examination, DoctorAvailability
import requests

from google.cloud import firestore as google_cloud_firestore


# Run task: celery -A OUPharmacyManagementApp.celery worker --pool=solo --loglevel=info

@shared_task
def load_waiting_room():
    try:
        current_day = datetime.now()
        now = timezone.now()
        print(current_day, now)
        exam_today = []
        today = current_day.replace(hour=0, minute=0, second=0)
        tomorrow = current_day.replace(hour=23, minute=59, second=59)
        print("today", today, 'tomorrow', tomorrow)
        today_utc = current_day.replace(hour=0, minute=0, second=0).astimezone(pytz.utc)
        tomorrow_utc = current_day.replace(hour=23, minute=59, second=59).astimezone(pytz.utc)
        print("today_utc", today_utc, 'tomorrow_utc', tomorrow_utc)
        examinations = Examination.objects.filter(created_date__range=(today_utc,
                                                                       tomorrow_utc)).order_by('created_date').all()

        total_examinations = len(examinations)
        for index, examination in enumerate(examinations):
            user = examination.user
            location = user.location
            doctor_availability = examination.doctor_availability
            lat = location.lat
            lng = location.lng
            res = requests.get('https://rsapi.goong.io/Direction', params={
                'origin': f'{os.getenv("MAP_ORIGIN_LAT")},{os.getenv("MAP_ORIGIN_LNG")}',
                'destination': f'{lat},{lng}',
                'vehicle': 'car',
                'api_key': os.getenv('MAP_APIKEY')
            })

            res_data = json.loads(res.text)

            start_time_str = doctor_availability.start_time.strftime("%H:%M:%S") if doctor_availability else None
            end_time_str = doctor_availability.end_time.strftime("%H:%M:%S") if doctor_availability else None

            data = {
                'isCommitted': False,
                'isStarted': False,
                'remindStatus': False,
                'examID': examination.id,
                'author': examination.user.email,
                'patientFullName': f'{examination.patient.first_name} {examination.patient.last_name}',
                'startedDate': current_day.strftime("%Y-%m-%d"),  # Update the value as per your requirement
                'startTime': start_time_str,
                'endTime': end_time_str,
                'doctorID': examination.doctor_availability.doctor.id if examination.doctor_availability else None,
                'distance': res_data.get('routes')[0].get('legs')[0].get('distance').get('text'),
                'duration': res_data.get('routes')[0].get('legs')[0].get('duration').get('value')
            }

            exam_today.append(data)

        database = firestore.client()
        doc_ref = database.collection('dev_waiting-room').document(str(current_day.date()))
        doc_ref.set({'exams': exam_today})

    except Exception as ex:
        print(ex)
        return "Add failed!"

    return "Add OKE!"


@shared_task
def task_load_waiting_room_by_doctor_availability():
    try:
        current_day = datetime.now()
        start_of_day = timezone.make_aware(datetime.combine(current_day.date(), datetime.min.time()))
        end_of_day = start_of_day + timedelta(days=1) - timedelta(microseconds=1)

        now = timezone.now()
        print("Current Day:", current_day)
        print("Now:", now)

        exam_today = []

        doctor_availabilities = DoctorAvailability.objects.filter(day=current_day.date()).select_related('doctor').order_by('start_time')

        for doctor_availability in doctor_availabilities:
            user = doctor_availability.doctor
            examinations = Examination.objects.filter(
                doctor_availability__day=current_day.date(),
                doctor_availability=doctor_availability,
                mail_status=True
            ).all()

            for examination in examinations:

                location = examination.user.location
                lat = location.lat
                lng = location.lng
                res = requests.get('https://rsapi.goong.io/Direction', params={
                    'origin': f'{os.getenv("MAP_ORIGIN_LAT")},{os.getenv("MAP_ORIGIN_LNG")}',
                    'destination': f'{lat},{lng}',
                    'vehicle': 'car',
                    'api_key': os.getenv('MAP_APIKEY')
                })

                res_data = json.loads(res.text)

                start_time_str = doctor_availability.start_time.strftime("%H:%M:%S")
                end_time_str = doctor_availability.end_time.strftime("%H:%M:%S")

                print(examination.doctor_availability)

                doctor_id = examination.doctor_availability.doctor_id

                data = {
                    'isCommitted': False,
                    'isStarted': False,
                    'remindStatus': False,
                    'examID': examination.id,
                    'author': examination.user.email,
                    'patientFullName': f'{examination.patient.first_name} {examination.patient.last_name}',
                    'startedDate': current_day.strftime("%Y-%m-%d"),  # Update the value as per your requirement
                    'startTime': start_time_str,
                    'endTime': end_time_str,
                    'doctorID': doctor_id,
                    'distance': res_data.get('routes')[0].get('legs')[0].get('distance').get('text'),
                    'duration': res_data.get('routes')[0].get('legs')[0].get('duration').get('value')
                }

                exam_today.append(data)

        database = firestore.client()
        doc_ref = database.collection('dev_waiting-room').document(str(current_day.date()))
        doc_ref.set({'exams': exam_today})

    except Exception as ex:
        print(ex)
        return "Add failed!"
    return "Add OKE!"


@shared_task
def job_send_email_re_examination():
    # Get the current date
    current_date = timezone.now().date()

    # Calculate the target date (one month before current date)
    target_date = current_date.replace(month=current_date.month - 1)

    print(current_date, target_date)

    # Retrieve examinations created one month ago
    examinations = Examination.objects.filter(created_date__lt=target_date).all()

    for examination in examinations:
        # Get the related user and patient
        user = examination.user
        patient = examination.patient

        if not user or not patient:
            continue  # Skip to the next examination if user or patient is not found

        # Check if the examination is already reminded
        if examination.reminder_email:
            continue  # Skip to the next examination if already reminded

        # Compose the email subject
        subject = "Nhắc nhở: Tái khám"

        # Format the created_date to "ĐD-MM-YYYY" format
        created_date_formatted = examination.created_date.strftime("%d-%m-%Y")

        # Compose the email content
        content = f"Xin chào {user.first_name} {user.last_name},\n\n" \
                  f"Đây là một lời nhắc nhở rằng đã một tháng kể từ lần khám trước của bạn. " \
                  f"Chúng tôi cần thông báo đến bạn, đặt lịch tái khám sớm nhất có thể để kiểm tra lại tình trạng sức khỏe của mình.\n\n" \
                  f"Họ tên bệnh nhân: {patient.first_name} {patient.last_name}\n" \
                  f"Mô tả: {examination.description}\n" \
                  f"Ngày tạo: {created_date_formatted}\n\n" \
                  f"Vui lòng liên hệ chúng tôi, hoặc lên trang chủ OUPharmacy để đặt lịch tái khám.\n\n" \
                  f"Cảm ơn bạn, chúc bạn một ngày mới thật nhiều sức khỏe!\n"

        # Send the reminder email
        try:
            send_email = EmailMessage(subject, content, to=[user.email])
            send_email.send()
        except Exception as e:
            print(f"Lỗi gửi email nhắc nhở đến {user.email}: {str(e)}")
        else:
            # Update the examination's reminder_email field
            examination.reminder_email = True
            examination.save()
            print('OKE')

    return print('OKE but no exams')