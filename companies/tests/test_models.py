from datetime import date

from django.db import connection
from django.test import TestCase
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from companies.models import Company, Domain


class CompanyModelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection.set_schema_to_public()

    def setUp(self):
        connection.set_schema_to_public()

    def test_create_company_and_domain(self):
        with schema_context(get_public_schema_name()):
            company = Company(
                schema_name="testco",
                name="Test Co",
                paid_until=date(2099, 1, 1),
                on_trial=True,
            )
            company.save()

            domain = Domain.objects.create(
                domain="testco.test.com",
                tenant=company,
                is_primary=True,
            )

            self.assertEqual(company.name, "Test Co")
            self.assertEqual(domain.tenant, company)
            self.assertEqual(company.get_primary_domain().domain, "testco.test.com")

            company.delete(force_drop=True)

    def test_auto_create_schema_creates_postgres_schema(self):
        with schema_context(get_public_schema_name()):
            company = Company.objects.create(
                schema_name="schematest",
                name="Schema Test Co",
                paid_until=date(2099, 1, 1),
                on_trial=False,
            )
            Domain.objects.create(
                domain="schematest.test.com",
                tenant=company,
                is_primary=True,
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = %s
                """,
                ["schematest"],
            )
            self.assertIsNotNone(cursor.fetchone())

        with schema_context(get_public_schema_name()):
            company.delete(force_drop=True)


class CompanyQueryTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection.set_schema_to_public()

    def setUp(self):
        connection.set_schema_to_public()

    def test_list_companies_on_public_schema(self):
        with schema_context(get_public_schema_name()):
            Company.objects.create(
                schema_name="alpha",
                name="Alpha",
                paid_until=date(2099, 1, 1),
                on_trial=True,
            )
            Company.objects.create(
                schema_name="beta",
                name="Beta",
                paid_until=date(2099, 1, 1),
                on_trial=False,
            )

            names = list(
                get_tenant_model()
                .objects.filter(schema_name__in=["alpha", "beta"])
                .order_by("name")
                .values_list("name", flat=True)
            )

            self.assertEqual(names, ["Alpha", "Beta"])

            for company in get_tenant_model().objects.filter(
                schema_name__in=["alpha", "beta"]
            ):
                company.delete(force_drop=True)
