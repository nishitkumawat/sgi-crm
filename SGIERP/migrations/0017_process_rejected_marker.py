from django.db import migrations, models


def create_rejected_process(apps, schema_editor):
    Process = apps.get_model('SGIERP', 'Process')
    db_alias = schema_editor.connection.alias
    rejected = Process.objects.using(db_alias).filter(name__iexact='Rejected').first()
    if rejected:
        if not rejected.is_completed_process:
            rejected.is_rejected_process = True
            rejected.save(update_fields=['is_rejected_process'], using=db_alias)
        return

    last_order = Process.objects.using(db_alias).order_by('-order').values_list('order', flat=True).first() or 0
    Process.objects.using(db_alias).create(
        name='Rejected',
        is_active=True,
        is_rejected_process=True,
        order=last_order + 1,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('SGIERP', '0016_backfill_item_created_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='process',
            name='is_rejected_process',
            field=models.BooleanField(
                default=False,
                help_text="Mark this as the special 'Rejected' process. Only one process should have this flag.",
            ),
        ),
        migrations.RunPython(create_rejected_process, migrations.RunPython.noop),
    ]
