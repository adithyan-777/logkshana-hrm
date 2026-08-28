import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0004_devicebrand_devicetype_device"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Domain",
        ),
        migrations.RemoveField(
            model_name="company",
            name="schema_name",
        ),
        migrations.AddField(
            model_name="company",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="company",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="company",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
