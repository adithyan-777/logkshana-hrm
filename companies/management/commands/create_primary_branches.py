from django.core.management.base import BaseCommand, CommandError

from companies.models import Company
from companies.services import companies_ensure_primary_branches


class Command(BaseCommand):
    help = (
        "Create a branch named 'primary' for each company in the database "
        "and assign it to employees that do not already have a branch."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            help="Company name. Defaults to every company.",
        )

    def handle(self, *args, **options):
        company_name = options.get("company")

        if company_name:
            try:
                companies = [Company.objects.get(name=company_name)]
            except Company.DoesNotExist as exc:
                raise CommandError(f"No company named '{company_name}'.") from exc
        else:
            companies = list(Company.objects.all())

        if not companies:
            self.stdout.write("No companies found.")
            return

        results = companies_ensure_primary_branches(companies=companies)

        for result in results:
            company = result["company"]
            status = "created" if result["branch_created"] else "existing"
            self.stdout.write(
                f"{company.name}: {status} primary branch, "
                f"assigned to {result['employees_updated']} employee(s)"
            )

        self.stdout.write(self.style.SUCCESS("Primary branches ready."))
