from django.db import migrations, models


def fill_usernames(apps, schema_editor):
    TenantUser = apps.get_model("users", "TenantUser")
    for user in TenantUser.objects.filter(username=""):
        local_part = (user.email or f"user{user.pk}").split("@", 1)[0]
        username = local_part or f"user{user.pk}"
        suffix = 1
        candidate = username
        while TenantUser.objects.filter(username=candidate).exclude(pk=user.pk).exists():
            suffix += 1
            candidate = f"{username}{suffix}"
        user.username = candidate
        user.save(update_fields=["username"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantuser",
            name="username",
            field=models.CharField(default="", max_length=150),
            preserve_default=False,
        ),
        migrations.RunPython(fill_usernames, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tenantuser",
            name="username",
            field=models.CharField(db_index=True, max_length=150, unique=True),
        ),
    ]
