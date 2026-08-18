from common.tests.base import BaseTenantTestCase
from common.tests.factories import employee_factory
from companies.models import Branch
from companies.services import (
    PRIMARY_BRANCH_CODE,
    PRIMARY_BRANCH_NAME,
    branch_create,
    companies_ensure_primary_branches,
    company_primary_branch_get_or_create,
)


class BranchCreateTests(BaseTenantTestCase):
    def test_creates_branch_for_company(self):
        branch = branch_create(name="HQ", company=self.tenant, code="HQ")

        self.assertEqual(branch.name, "HQ")
        self.assertEqual(branch.code, "HQ")
        self.assertEqual(branch.company_id, self.tenant.id)


class CompanyPrimaryBranchTests(BaseTenantTestCase):
    def test_creates_primary_branch_when_missing(self):
        branch, created = company_primary_branch_get_or_create(company=self.tenant)

        self.assertTrue(created)
        self.assertEqual(branch.name, PRIMARY_BRANCH_NAME)
        self.assertEqual(branch.code, PRIMARY_BRANCH_CODE)
        self.assertEqual(branch.company_id, self.tenant.id)

    def test_returns_existing_primary_branch(self):
        first, created_first = company_primary_branch_get_or_create(company=self.tenant)
        second, created_second = company_primary_branch_get_or_create(company=self.tenant)

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            Branch.objects.filter(company=self.tenant, name=PRIMARY_BRANCH_NAME).count(),
            1,
        )


class CompaniesEnsurePrimaryBranchesTests(BaseTenantTestCase):
    def test_assigns_primary_branch_to_employees_without_one(self):
        employee = employee_factory(first_name="No", last_name="Branch", emp_code="NB001")
        self.assertIsNone(employee.branch_id)

        results = companies_ensure_primary_branches(companies=[self.tenant])

        employee.refresh_from_db()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["branch_created"])
        self.assertEqual(results[0]["employees_updated"], 1)
        self.assertEqual(employee.branch_id, results[0]["branch"].id)

    def test_does_not_overwrite_existing_employee_branch(self):
        other_branch = branch_create(name="other", company=self.tenant, code="OTHER")
        employee = employee_factory(first_name="Has", last_name="Branch", emp_code="HB001")
        employee.branch = other_branch
        employee.save(update_fields=["branch"])

        results = companies_ensure_primary_branches(companies=[self.tenant])

        employee.refresh_from_db()
        self.assertEqual(results[0]["employees_updated"], 0)
        self.assertEqual(employee.branch_id, other_branch.id)

    def test_is_idempotent(self):
        employee_factory(first_name="Once", last_name="Assigned", emp_code="OA001")

        first = companies_ensure_primary_branches(companies=[self.tenant])
        second = companies_ensure_primary_branches(companies=[self.tenant])

        self.assertTrue(first[0]["branch_created"])
        self.assertFalse(second[0]["branch_created"])
        self.assertEqual(first[0]["employees_updated"], 1)
        self.assertEqual(second[0]["employees_updated"], 0)
        self.assertEqual(
            Branch.objects.filter(company=self.tenant, name=PRIMARY_BRANCH_NAME).count(),
            1,
        )
