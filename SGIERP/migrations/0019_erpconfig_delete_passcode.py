from django.contrib.auth.hashers import make_password
from django.db import migrations, models


def seed_delete_passcode(apps, schema_editor):
    ERPConfig = apps.get_model('SGIERP', 'ERPConfig')
    ERPConfig.objects.update_or_create(
        id=1,
        defaults={'delete_passcode_hash': make_password('1234')},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('SGIERP', '0018_optional_dispatch_machine'),
    ]

    operations = [
        migrations.AddField(
            model_name='erpconfig',
            name='delete_passcode_hash',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.RunPython(seed_delete_passcode, migrations.RunPython.noop),
    ]
