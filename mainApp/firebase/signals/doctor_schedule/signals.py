import os

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from OUPharmacyManagementApp.firebase_config import get_firestore
from mainApp.models import DoctorSchedule, TimeSlot, Examination, Patient, Bill

db = get_firestore()

def get_collection_name():
    """Get the appropriate collection name based on environment"""
    env = os.getenv('ENVIRONMENT', 'dev').lower()  # Default to 'dev' if not set
    if env == 'production':
        return 'production_doctor_schedule'
    elif env == 'staging':
        return 'staging_doctor_schedule'
    else:
        return 'dev_doctor_schedule'

def sync_schedules_by_date(date):
    """Sync all doctor schedules for a specific date to Firebase"""
    try:
        # Get all schedules for this date
        schedules = DoctorSchedule.objects.filter(date=date)
        
        if not schedules.exists():
            # If no schedules exist for this date, delete the document
            collection_name = get_collection_name()
            db.collection(collection_name).document(date.isoformat()).delete()
            print(f"No schedules for {date}, document deleted from Firebase.")
            return
            
        # Create a document with all schedules for this date
        date_data = {
            'date': date.isoformat(),
            'schedules': []
        }
        
        # Add each schedule to the document
        for schedule in schedules:
            schedule_data = {
                'id': schedule.id,
                'doctor_id': schedule.doctor.id,
                'doctor_name': f"{schedule.doctor.first_name} {schedule.doctor.last_name}",
                'doctor_email': schedule.doctor.email,
                'session': schedule.session,
                'is_off': schedule.is_off,
                'time_slots': []
            }
            
            # Get all time slots for this schedule
            time_slots = TimeSlot.objects.filter(schedule=schedule)
            waiting_status_undone = 'undone'
            # waiting_status_processing = 'processing'
            # waiting_status_done = 'done'
            for slot in time_slots:
                # Check if this time slot has an examination (patient)
                patient_info = None
                appointment_infor = None
                examinations = Examination.objects.filter(time_slot=slot, active=True)
                examination = examinations.select_related('patient').first()
                
                if examination and examination.patient:
                    patient_info = {
                        'id': examination.patient.id,
                        'name': f"{examination.patient.first_name} {examination.patient.last_name}",
                        'dob': examination.patient.date_of_birth.isoformat() if examination.patient.date_of_birth else None,
                        'gender': examination.patient.gender,
                        'email': examination.patient.email
                    }
                    appointment_infor = {
                        'id': examination.id,
                        'user': {'id': examination.user.id, 'email': examination.user.email,
                                 'name': examination.user.first_name + " " + examination.user.last_name},
                    }
                else:
                    print(f"Debug - TimeSlot {slot.id}: No patient found. Examination: {examination}")
                
                schedule_data['time_slots'].append({
                    'id': slot.id,
                    "appointment_info":appointment_infor,
                    'start_time': slot.start_time.isoformat(),
                    'end_time': slot.end_time.isoformat(),
                    'is_available': slot.is_available,
                    'status': waiting_status_undone,
                    'patient_info': patient_info
                })
            
            date_data['schedules'].append(schedule_data)
        
        # Save to Firestore using the date as document ID
        collection_name = get_collection_name()
        db.collection(collection_name).document(date.isoformat()).set(date_data)
        print(f"All schedules for {date} synced to Firebase collection: {collection_name}")
        
    except Exception as e:
        print(f"Error syncing schedules for {date} to Firebase: {e}")

@receiver(post_save, sender=DoctorSchedule)
def sync_doctor_schedule_to_firebase(sender, instance, **kwargs):
    """Sync doctor schedule to Firebase when created or updated"""
    try:
        # Sync all schedules for this date
        sync_schedules_by_date(instance.date)
    except Exception as e:
        print(f"Error syncing doctor schedule {instance.id} to Firebase: {e}")

@receiver(post_delete, sender=DoctorSchedule)
def delete_doctor_schedule_from_firebase(sender, instance, **kwargs):
    """Update Firebase when a doctor schedule is deleted"""
    try:
        # Sync all remaining schedules for this date (or delete document if none left)
        sync_schedules_by_date(instance.date)
    except Exception as e:
        print(f"Error updating Firebase after doctor schedule {instance.id} deletion: {e}")

@receiver(post_save, sender=TimeSlot)
def sync_time_slot_to_firebase(sender, instance, **kwargs):
    """Sync time slot to Firebase when created or updated"""
    try:
        # When a time slot is updated, update the document for that date
        if hasattr(instance, 'schedule') and instance.schedule:
            sync_schedules_by_date(instance.schedule.date)
    except Exception as e:
        print(f"Error syncing time slot {instance.id} to Firebase: {e}")

@receiver(post_delete, sender=TimeSlot)
def delete_time_slot_from_firebase(sender, instance, **kwargs):
    """Update Firebase when a time slot is deleted"""
    try:
        # When a time slot is deleted, update the document for that date
        if hasattr(instance, 'schedule') and instance.schedule:
            sync_schedules_by_date(instance.schedule.date)
    except Exception as e:
        print(f"Error updating Firebase after time slot {instance.id} deletion: {e}")

@receiver(post_save, sender=Examination)
def sync_examination_to_firebase(sender, instance, created, **kwargs):
    """Sync examination changes to Firebase"""
    try:
        if instance.time_slot and instance.time_slot.schedule:
            sync_schedules_by_date(instance.time_slot.schedule.date)
    except Exception as e:
        print(f"Error syncing examination {instance.id} to Firebase: {e}")

@receiver(post_delete, sender=Examination)
def delete_examination_from_firebase(sender, instance, **kwargs):
    """Update Firebase when an examination is deleted by removing the time slot"""
    try:
        if instance.time_slot and instance.time_slot.schedule:
            # Get the current document
            collection_name = get_collection_name()
            date = instance.time_slot.schedule.date
            doc_ref = db.collection(collection_name).document(date.isoformat())
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                # Find the schedule
                for schedule in data['schedules']:
                    if schedule['id'] == instance.time_slot.schedule.id:
                        # Remove the time slot
                        schedule['time_slots'] = [
                            ts for ts in schedule['time_slots'] 
                            if ts['id'] != instance.time_slot.id
                        ]
                        break

                # Update the document
                doc_ref.set(data)
    except Exception as e:
        print(f"Error updating Firebase after examination {instance.id} deletion: {e}")

@receiver(post_save, sender=Patient)
def sync_patient_to_firebase(sender, instance, **kwargs):
    """Sync patient changes to Firebase by updating all related examinations"""
    try:
        # Find all active examinations for this patient
        examinations = Examination.objects.filter(patient=instance, active=True)
        for examination in examinations:
            if examination.time_slot and examination.time_slot.schedule:
                sync_schedules_by_date(examination.time_slot.schedule.date)
    except Exception as e:
        print(f"Error syncing patient {instance.id} changes to Firebase: {e}")