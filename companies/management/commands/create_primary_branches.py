from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from companies.services import companies_ensure_primary_branches


class Command(BaseCommand):
    help = (
        "Create a branch named 'primary' for each company in the database "
        "and assign it to employees that do not already have a branch."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            help="Tenant schema name. Defaults to every company except the public schema.",
        )

    def handle(self, *args, **options):
        tenant_model = get_tenant_model()
        schema_name = options.get("schema")

        with schema_context(get_public_schema_name()):
            if schema_name:
                try:
                    companies = [tenant_model.objects.get(schema_name=schema_name)]
                except tenant_model.DoesNotExist as exc:
                    raise CommandError(f"No tenant with schema '{schema_name}'.") from exc
            else:
                companies = list(
                    tenant_model.objects.exclude(schema_name=get_public_schema_name())
                )

        if not companies:
            self.stdout.write("No companies found.")
            return

        results = companies_ensure_primary_branches(companies=companies)

        for result in results:
            company = result["company"]
            status = "created" if result["branch_created"] else "existing"
            self.stdout.write(
                f"{company.name} ({company.schema_name}): {status} primary branch, "
                f"assigned to {result['employees_updated']} employee(s)"
            )

        self.stdout.write(self.style.SUCCESS("Primary branches ready."))
