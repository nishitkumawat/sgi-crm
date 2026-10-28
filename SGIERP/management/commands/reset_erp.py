from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from SGIERP.models import (
    ERPUserProfile, Item, Process, ItemProcess, Assignee,
    Machine, MachineDispatch, DispatchComponent, StockHistory
)


class Command(BaseCommand):
    help = 'Reset ERP database - delete all data and create admin user'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting ERP database reset...'))

        # Delete in reverse order of dependencies
        models_to_delete = [
            ('DispatchComponent', DispatchComponent),
            ('MachineDispatch', MachineDispatch),
            ('Machine', Machine),
            ('StockHistory', StockHistory),
            ('ItemProcess', ItemProcess),
            ('Item', Item),
            ('Assignee', Assignee),
            ('Process', Process),
            ('ERPUserProfile', ERPUserProfile),
            ('User', User),
        ]

        for model_name, model in models_to_delete:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f'Deleted {count} {model_name} records'))

        # Create admin user
        admin_user = User.objects.create_user(
            username='admin',
            email='admin@shreegayatri-industries.com',
            password='12345678',
            first_name='Admin',
            last_name='User'
        )

        # Create ERP profile for admin
        ERPUserProfile.objects.create(
            user=admin_user,
            role='admin',
            department='Administration',
            phone='',
            is_erp_active=True
        )

        self.stdout.write(self.style.SUCCESS('Created admin user: admin / 12345678'))
        self.stdout.write(self.style.SUCCESS('ERP database reset complete!'))
