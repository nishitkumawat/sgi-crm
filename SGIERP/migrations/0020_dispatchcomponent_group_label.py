from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SGIERP', '0019_erpconfig_delete_passcode'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispatchcomponent',
            name='group_label',
            field=models.CharField(
                blank=True,
                default='',
                max_length=200,
                help_text="Display group label, e.g. 'Machine: MC001 (2×)' or 'Item: 430501'",
            ),
        ),
    ]
