from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from OUPharmacyManagementApp.firebase_config import get_firestore
from mainApp.models import DoctorSchedule, TimeSlot

db = get_firestore()

def sync_schedules_by_date(date):
    """Sync all doctor schedules for a specific date to Firebase"""
    try:
        # Get all schedules for this date
        schedules = DoctorSchedule.objects.filter(date=date)
        
        if not schedules.exists():
            # If no schedules exist for this date, delete the document
            collection_name = 'doctor_schedule'
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
            for slot in time_slots:
                schedule_data['time_slots'].append({
                    'id': slot.id,
                    'start_time': slot.start_time.isoformat(),
                    'end_time': slot.end_time.isoformat(),
                    'is_available': slot.is_available
                })
            
            date_data['schedules'].append(schedule_data)
        
        # Save to Firestore using the date as document ID
        collection_name = 'doctor_schedule'
        db.collection(collection_name).document(date.isoformat()).set(date_data)
        print(f"All schedules for {date} synced to Firebase.")
        
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