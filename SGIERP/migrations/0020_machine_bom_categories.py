from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('SGIERP', '0019_erpconfig_delete_passcode')]

    operations = [
        migrations.AddField(
            model_name='machine', name='bom_categories',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='machinebom', name='category',
            field=models.CharField(default='Open', max_length=100),
        ),
    ]
