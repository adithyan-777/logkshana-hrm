from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django_tenants.utils import (
    get_public_schema_name,
    get_tenant_model,
    schema_context,
)

from employees.models import Employee
from employees.services import employee_username
from users.models import User


class Command(BaseCommand):
    help = (
        "Rewrite login usernames to the tenant-safe "
        "'{firstname}{emp_code}.{schema}' format (e.g. janee001.freshline). "
        "Applies to employees with a linked user account and a non-blank "
        "emp_code; idempotent on re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            help=(
                "Tenant schema name. Defaults to every company except "
                "the public schema."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the changes without saving.",
        )

    def handle(self, *args, **options):
        tenant_model = get_tenant_model()
        schema_name = options.get("schema")
        public_schema = get_public_schema_name()
        dry_run = options["dry_run"]

        with schema_context(public_schema):
            if schema_name:
                if schema_name == public_schema:
                    raise CommandError("Usernames are tenant-scoped, not public.")
                try:
                    tenants = [tenant_model.objects.get(schema_name=schema_name)]
                except tenant_model.DoesNotExist as exc:
                    raise CommandError(
                        f"No tenant with schema '{schema_name}'."
                    ) from exc
            else:
                tenants = list(tenant_model.objects.exclude(schema_name=public_schema))

        if not tenants:
            self.stdout.write("No tenants found.")
            return

        totals = {"updated": 0, "already": 0, "skipped": 0, "collided": 0}
        style = self.style.MIGRATE_LABEL if not dry_run else self.style.WARNING
        for tenant in tenants:
            updated, already, skipped, conflicts = self._rewrite_tenant(
                tenant, dry_run=dry_run
            )
            totals["updated"] += updated
            totals["already"] += already
            totals["skipped"] += skipped
            totals["collided"] += len(conflicts)
            self.stdout.write(
                f"{tenant.name} ({tenant.schema_name}): "
                f"{updated} renamed, {already} already ok, {skipped} skipped, "
                f"{len(conflicts)} collided"
            )
            for conflict in conflicts:
                emp_code, employee_name, target, taken_by = conflict
                self.stdout.write(
                    f"  CONFLICT {tenant.schema_name}: '{employee_name}' "
                    f"(emp_code {emp_code}) wanted '{target}' but it is taken "
                    f"by '{taken_by}' — left unchanged."
                )

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            style(
                f"{prefix}Done: {totals['updated']} updated, "
                f"{totals['already']} already ok, {totals['skipped']} skipped, "
                f"{totals['collided']} collided."
            )
        )

    def _rewrite_tenant(self, tenant, *, dry_run: bool):
        """Rewrite usernames inside one tenant schema.

        Returns (updated, already_ok, skipped, conflicts) where each conflict
        row is (emp_code, employee_name, desired_username, taken_by).
        """
        updated = already = skipped = 0
        conflicts: list[tuple[str, str, str, str]] = []

        with schema_context(tenant.schema_name):
            employees = (
                Employee.objects.select_related("user")
                .filter(user__isnull=False)
                .exclude(emp_code=None)
                .exclude(emp_code="")
            )
            for employee in employees:
                target = employee_username(
                    first_name=employee.first_name,
                    emp_code=employee.emp_code,
                    schema_name=tenant.schema_name,
                )
                user = employee.user
                if user.username == target:
                    already += 1
                    continue
                # Usernames are unique across all tenants (shared public
                # table), so a match on any *other* account blocks the
                # rename. Case-insensitive like UsernameUniquenessMixin in
                # users/forms.py.
                taken_by = (
                    User.objects.filter(username__iexact=target)
                    .exclude(pk=user.pk)
                    .values_list("username", flat=True)
                    .first()
                )
                if taken_by is not None:
                    conflicts.append(
                        (
                            employee.emp_code,
                            employee.full_name,
                            target,
                            taken_by,
                        )
                    )
                    continue
                if dry_run:
                    self.stdout.write(
                        f"  {tenant.schema_name}: '{employee.full_name}' "
                        f"(emp_code {employee.emp_code}) "
                        f"'{user.username}' -> '{target}'"
                    )
                else:
                    with schema_context(get_public_schema_name()):
                        user.username = target
                        user.save(update_fields=["username"])
                updated += 1

            skip_qs = Employee.objects.all().filter(
                Q(user__isnull=True) | Q(emp_code=None) | Q(emp_code="")
            )
            skipped = skip_qs.count()
        return updated, already, skipped, conflicts
