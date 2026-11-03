from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('SGIERP', '0017_process_rejected_marker')]
    operations = [
        migrations.AlterField(
            model_name='machinedispatch', name='machine',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='dispatches', to='SGIERP.machine'),
        ),
    ]
