from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('SGIERP', '0013_erp_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='erpconfig',
            name='primary_theme',
            field=models.CharField(choices=[('orange', 'Orange'), ('blue', 'Blue'), ('green', 'Green'), ('purple', 'Purple'), ('red', 'Red')], default='orange', max_length=20),
        ),
    ]
