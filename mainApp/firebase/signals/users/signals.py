import os

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.conf import settings

from OUPharmacyManagementApp.firebase_config import get_firestore

User = get_user_model()
db = get_firestore()

@receiver(post_save, sender=User)
def sync_user_to_firebase(sender, instance, created, **kwargs):
    """Sync user to Firebase when created or updated"""
    user_data = {
        'email': instance.email,
        'fullName': f"{instance.first_name} {instance.last_name}",
        'id': instance.id,
        'avatar': instance.avatar.url if instance.avatar else None,
        'lastSeen': instance.last_login.isoformat() if instance.last_login else None,
    }

    try:
        # Use a dynamic collection name based on the environment (optional)
        collection_name = 'dev_users' if os.getenv('ENVIRONMENT') == 'dev' else 'production_users'

        # Save to Firestore
        db.collection(collection_name).document(str(instance.id)).set(user_data)

        # Log success (optional)
        if created:
            print(f"User {instance.email} created and synced to Firebase.")
        else:
            print(f"User {instance.email} updated and synced to Firebase.")
    except Exception as e:
        # Log the error (replace with your logging mechanism)
        print(f"Error syncing user {instance.email} to Firebase: {e}")

@receiver(post_delete, sender=User)
def delete_user_from_firebase(sender, instance, **kwargs):
    """Delete user from Firebase when deleted in Django"""
    try:
        # Use a dynamic collection name based on the environment (optional)
        collection_name = 'dev_users' if os.getenv('ENVIRONMENT') == 'dev' else 'production_users'

        # Delete from Firestore
        db.collection(collection_name).document(str(instance.id)).delete()

        # Log success (optional)
        print(f"User {instance.email} deleted from Firebase.")
    except Exception as e:
        # Log the error (replace with your logging mechanism)
        print(f"Error deleting user {instance.email} from Firebase: {e}")