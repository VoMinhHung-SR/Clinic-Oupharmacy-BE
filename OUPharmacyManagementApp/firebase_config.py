import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Firebase configuration
def initialize_firebase():
    """Initialize Firebase Admin SDK with environment variables"""
    if not firebase_admin._apps:
        # Determine environment
        is_prod = os.getenv('ENVIRONMENT', 'dev') == 'production'
        
        if is_prod and os.path.exists(os.getenv('FIREBASE_CREDENTIALS_PATH', '')):
            # Production: Use JSON file for credentials (more secure)
            cred = credentials.Certificate(os.getenv('FIREBASE_CREDENTIALS_PATH'))
        else:
            # Development or fallback: Use environment variables
            cred_dict = {
                "type": "service_account",
                "project_id": os.getenv('FIREBASE_PROJECT_ID'),
                "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n') if os.getenv('FIREBASE_PRIVATE_KEY') else None,
                "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
                "client_id": os.getenv('FIREBASE_CLIENT_ID'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_CERT_URL')
            }
            cred = credentials.Certificate(cred_dict)
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.getenv('FIREBASE_DATABASE_URL')
        })
    
    return firebase_admin

# Get Firestore instance
def get_firestore():
    """Get the Firestore database instance"""
    try:
        initialize_firebase()
        return firestore.client()
    except Exception as e:
        print(f"Error initializing Firestore: {e}")
        return None

# Get Auth instance
def get_auth():
    """Get the Firebase Auth instance"""
    try:
        initialize_firebase()
        return auth
    except Exception as e:
        print(f"Error initializing Firebase Auth: {e}")
        return None 