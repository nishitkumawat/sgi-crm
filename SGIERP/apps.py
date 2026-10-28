from django.apps import AppConfig


class SgierPConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'SGIERP'
    verbose_name = 'SGI ERP'

    def ready(self):
        pass
