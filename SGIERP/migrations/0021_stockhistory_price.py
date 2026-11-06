from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('SGIERP', '0020_machine_bom_categories')]
    operations = [
        migrations.AddField(
            model_name='itemprocess',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='stockhistory',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
