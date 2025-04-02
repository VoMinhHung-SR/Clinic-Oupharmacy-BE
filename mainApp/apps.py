from django.apps import AppConfig


class MainappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mainApp'

    def ready(self):
        # Temporarily disabled Firebase signals
        # import mainApp.firebase.signals.users.signals
        pass