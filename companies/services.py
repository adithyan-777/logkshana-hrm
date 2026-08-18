from django_tenants.utils import get_public_schema_name, schema_context

from companies.models import Branch, Company

PRIMARY_BRANCH_NAME = "primary"
PRIMARY_BRANCH_CODE = "PRIMARY"


def branch_create(*, name: str, company: Company, code: str | None = None) -> Branch:
    branch = Branch(name=name, company=company, code=code)
    branch.full_clean()
    branch.save()
    return branch


def company_primary_branch_get_or_create(*, company: Company) -> tuple[Branch, bool]:
    branch = Branch.objects.filter(company=company, name=PRIMARY_BRANCH_NAME).first()
    if branch is not None:
        return branch, False

    return (
        branch_create(
            name=PRIMARY_BRANCH_NAME,
            company=company,
            code=PRIMARY_BRANCH_CODE,
        ),
        True,
    )


def companies_ensure_primary_branches(*, companies=None) -> list[dict]:
    """Create a 'primary' branch for each company and assign it to employees without one."""
    from employees.models import Employee

    if companies is None:
        companies = Company.objects.exclude(schema_name=get_public_schema_name())

    results = []
    for company in companies:
        branch, created = company_primary_branch_get_or_create(company=company)
        employees_updated = 0
        if company.schema_name != get_public_schema_name():
            with schema_context(company.schema_name):
                employees_updated = Employee.objects.filter(branch__isnull=True).update(
                    branch=branch
                )

        results.append(
            {
                "company": company,
                "branch": branch,
                "branch_created": created,
                "employees_updated": employees_updated,
            }
        )

    return results
