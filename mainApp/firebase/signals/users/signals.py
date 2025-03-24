from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
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
    
    # Save to Firestore in the 'dev_users' collection
    db.collection('users').document(str(instance.id)).set(user_data)

@receiver(post_delete, sender=User)
def delete_user_from_firebase(sender, instance, **kwargs):
    """Delete user from Firebase when deleted in Django"""
    db.collection('users').document(str(instance.id)).delete() 