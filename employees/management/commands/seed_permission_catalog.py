from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from employees.services import permission_catalog_ensure


class Command(BaseCommand):
    help = (
        "Ensure the built-in permission catalog exists in one or all "
        "company tenant schemas."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            help="Tenant schema name. Defaults to every company except the public schema.",
        )

    def handle(self, *args, **options):
        tenant_model = get_tenant_model()
        schema_name = options.get("schema")
        public_schema = get_public_schema_name()

        with schema_context(public_schema):
            if schema_name:
                if schema_name == public_schema:
                    raise CommandError("Permission catalog is tenant-scoped, not public.")
                try:
                    tenants = [tenant_model.objects.get(schema_name=schema_name)]
                except tenant_model.DoesNotExist as exc:
                    raise CommandError(
                        f"No tenant with schema '{schema_name}'."
                    ) from exc
            else:
                tenants = list(
                    tenant_model.objects.exclude(schema_name=public_schema)
                )

        if not tenants:
            self.stdout.write("No tenants found.")
            return

        for tenant in tenants:
            with schema_context(tenant.schema_name):
                permissions = permission_catalog_ensure()
            self.stdout.write(
                f"{tenant.name} ({tenant.schema_name}): "
                f"{len(permissions)} permission(s) ready"
            )

        self.stdout.write(self.style.SUCCESS("Permission catalog ready."))
