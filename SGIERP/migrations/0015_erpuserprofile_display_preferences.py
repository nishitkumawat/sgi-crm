from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('SGIERP', '0014_erpconfig_primary_theme'),
    ]

    operations = [
        migrations.AddField(
            model_name='erpuserprofile',
            name='default_per_page',
            field=models.CharField(default='20', max_length=10),
        ),
        migrations.AddField(
            model_name='erpuserprofile',
            name='primary_theme',
            field=models.CharField(default='orange', max_length=20),
        ),
    ]
