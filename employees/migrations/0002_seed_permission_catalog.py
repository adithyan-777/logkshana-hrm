from django.db import migrations


def seed_permission_catalog(apps, schema_editor):
    Permission = apps.get_model("employees", "Permission")
    from employees.permission_catalog import permission_catalog_entries

    for entry in permission_catalog_entries():
        Permission.objects.update_or_create(
            codename=entry["codename"],
            defaults={
                "name": entry["name"],
                "description": entry["description"],
            },
        )


def unseed_permission_catalog(apps, schema_editor):
    Permission = apps.get_model("employees", "Permission")
    from employees.permission_catalog import PermissionCodename

    Permission.objects.filter(codename__in=PermissionCodename.values).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_permission_catalog, unseed_permission_catalog),
    ]
