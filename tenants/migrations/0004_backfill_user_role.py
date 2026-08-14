from django.db import migrations


def backfill_roles(apps, schema_editor):
    User = apps.get_model('tenants', 'User')
    # Anyone who was staff/super-admin under the old scheme becomes OWNER
    # so they don't lose access to anything on deploy. Everyone else keeps
    # the default STAFF and can be promoted to MANAGER from the admin.
    User.objects.filter(is_super_admin=True).update(role='OWNER')
    User.objects.filter(is_super_admin=False, is_staff=True).update(role='OWNER')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_user_role'),
    ]

    operations = [
        migrations.RunPython(backfill_roles, noop_reverse),
    ]
