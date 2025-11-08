from django.apps import AppConfig


class StoreappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'storeApp'
    
    def ready(self):
        import storeApp.admin  # Make sure admin is imported when app starts