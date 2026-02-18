# auth_app/apps.py
from django.apps import AppConfig

class AuthAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auth_app'

    def ready(self):
        # This runs onces when Django starts
        import auth_app.logger
