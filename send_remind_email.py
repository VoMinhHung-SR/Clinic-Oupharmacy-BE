import datetime
import os
import sys
import django
from django.core.mail import EmailMessage
# Import the Examination model
from mainApp.models import Examination


# Set up the Django environment
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OUPharmacyManagementApp.settings')
django.setup()


def send_reexam_reminder_email(examination):
    # Get the user and patient associated with the examination
    user = examination.user
    patient = examination.patient

    # Calculate the date for the re-examination
    reexam_date = examination.created_date + datetime.timedelta(minutes=30)
    reexam_date_str = reexam_date.strftime('%d-%m-%Y')

    # Modify the email content and send the reminder email to the user
    current_date = datetime.date.today().strftime('%d-%m-%Y')
    subject = "Nhắc nhở tái khám"
    to_user = user.email
    content = f"""Xin chào {user.first_name + " " + user.last_name},

Đây là một email nhắc nhở về lịch tái khám của bạn tại OUPharmacy vào ngày {reexam_date_str}.

Chi tiết lịch tái khám của {user.username}:
(+)  Mã đặt lịch: {examination.pk}
(+)  Họ tên bệnh nhân: {patient.first_name} {patient.last_name}
(+)  Mô tả: {examination.description}
(+)  Ngày tái khám: {reexam_date_str}
=====================
(-)  Phí khám của bạn là: {examination.wage:,.0f} VND

Địa điểm: 371 Nguyễn Kiệm, Phường 3, Gò Vấp, Thành phố Hồ Chí Minh

Vui lòng đến tái khám đúng giờ và chuẩn bị sẵn các giấy tờ cần thiết.

OUPharmacy xin chúc bạn sức khỏe và một buổi tái khám tốt lành, xin chân thành cả́m ơn."""

    try:
        if content and subject and to_user:
            send_email = EmailMessage(subject, content, to=[to_user])
            send_email.send()
            examination.reminder_email = True
            examination.save()
    except Exception as e:
        print(f"Error sending email: {str(e)}")


def send_reminder_emails():
    # Get the current date and time
    now = datetime.datetime.now()

    # Calculate the date for the earliest re-examination
    earliest_reexam_date = now + datetime.timedelta(minutes=30)

    # Find the examinations that need to be reminded
    exams_to_remind = Examination.objects.filter(
        reminder_email=False,
        created_date__lte=earliest_reexam_date
    )

    # Send reminder emails for each examination
    for exam in exams_to_remind:
        send_reexam_reminder_email(exam)
