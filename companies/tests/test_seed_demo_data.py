from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from common.tests.base import BaseTenantTestCase
from companies.models import Company, Domain
from employees.models import Employee


class SeedDemoDataCommandTests(BaseTenantTestCase):
    def test_refuses_public_schema(self):
        with self.assertRaisesMessage(CommandError, "public schema"):
            call_command("seed_demo_data", schema=get_public_schema_name())

    def test_seeds_employees_in_tenant_schema(self):
        domain = f"{self.tenant.schema_name}.demo.test"
        out = StringIO()

        call_command(
            "seed_demo_data",
            schema=self.tenant.schema_name,
            domain=domain,
            stdout=out,
            verbosity=0,
        )

        with schema_context(self.tenant.schema_name):
            self.assertTrue(Employee.objects.filter(emp_code="DEMO-001").exists())
        self.assertTrue(
            Domain.objects.filter(domain=domain, tenant=self.tenant).exists()
        )

    def test_moves_domain_from_public_tenant(self):
        domain = f"move-{self.tenant.schema_name}.test"

        with schema_context(get_public_schema_name()):
            public_company = Company.objects.filter(
                schema_name=get_public_schema_name()
            ).first()
            if public_company is None:
                public_company = Company(
                    schema_name=get_public_schema_name(),
                    name="Public",
                    paid_until=date(2099, 1, 1),
                    on_trial=True,
                )
                public_company.auto_create_schema = False
                public_company.save()
            Domain.objects.create(
                domain=domain,
                tenant=public_company,
                is_primary=False,
            )

        call_command(
            "seed_demo_data",
            schema=self.tenant.schema_name,
            domain=domain,
            verbosity=0,
        )

        moved = Domain.objects.select_related("tenant").get(domain=domain)
        self.assertEqual(moved.tenant_id, self.tenant.id)
        with schema_context(self.tenant.schema_name):
            self.assertTrue(Employee.objects.filter(emp_code="DEMO-001").exists())

    def test_attaches_conventional_subdomain(self):
        from django.conf import settings

        base_domain = getattr(settings, "BASE_DOMAIN", None)
        if not base_domain:
            self.skipTest("BASE_DOMAIN is not configured")
        domain = f"conv-{self.tenant.schema_name}.test"

        call_command(
            "seed_demo_data",
            schema=self.tenant.schema_name,
            domain=domain,
            verbosity=0,
        )

        expected = f"{self.tenant.schema_name}.{base_domain}"
        self.assertTrue(
            Domain.objects.filter(domain=expected, tenant=self.tenant).exists()
        )

    def test_skip_subdomain_and_extra_domains(self):
        from django.conf import settings

        domain = f"extra-{self.tenant.schema_name}.test"

        call_command(
            "seed_demo_data",
            schema=self.tenant.schema_name,
            domain=domain,
            extra_domains="extra1.test, extra2.test",
            skip_subdomain=True,
            verbosity=0,
        )

        base_domain = getattr(settings, "BASE_DOMAIN", None)
        if base_domain:
            conventional = f"{self.tenant.schema_name}.{base_domain}"
            self.assertFalse(Domain.objects.filter(domain=conventional).exists())
        self.assertTrue(
            Domain.objects.filter(domain="extra1.test", tenant=self.tenant).exists()
        )
        self.assertTrue(
            Domain.objects.filter(domain="extra2.test", tenant=self.tenant).exists()
        )
