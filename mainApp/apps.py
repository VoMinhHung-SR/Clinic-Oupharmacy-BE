from django.apps import AppConfig


class MainappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mainApp'

    def ready(self):
        import mainApp.firebase.signals.users.signals  # noqa: F401
        import mainApp.firebase.signals.doctor_schedule.signals