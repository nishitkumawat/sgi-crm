from django.db import migrations


def assign_existing_items_to_admin(apps, schema_editor):
    Item = apps.get_model('SGIERP', 'Item')
    ERPUserProfile = apps.get_model('SGIERP', 'ERPUserProfile')
    admin_profile = ERPUserProfile.objects.filter(role='admin').order_by('user_id').first()
    if admin_profile:
        Item.objects.filter(created_by__isnull=True).update(created_by_id=admin_profile.user_id)


class Migration(migrations.Migration):
    dependencies = [
        ('SGIERP', '0015_erpuserprofile_display_preferences'),
    ]

    operations = [
        migrations.RunPython(assign_existing_items_to_admin, migrations.RunPython.noop),
    ]
