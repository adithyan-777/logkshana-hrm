from datetime import date

from django.test import TestCase

from companies.models import Company


class CompanyModelTests(TestCase):
    def test_create_company(self):
        company = Company.objects.create(
            name="Test Co",
            paid_until=date(2099, 1, 1),
            on_trial=True,
        )

        self.assertEqual(company.name, "Test Co")
        self.assertTrue(company.on_trial)
        self.assertEqual(str(company), "Test Co")


class CompanyQueryTests(TestCase):
    def test_list_companies(self):
        Company.objects.create(
            name="Alpha",
            paid_until=date(2099, 1, 1),
            on_trial=True,
        )
        Company.objects.create(
            name="Beta",
            paid_until=date(2099, 1, 1),
            on_trial=False,
        )

        names = list(Company.objects.order_by("name").values_list("name", flat=True))

        self.assertEqual(names, ["Alpha", "Beta"])
