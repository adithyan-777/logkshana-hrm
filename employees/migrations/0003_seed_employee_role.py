from django.db import migrations


def seed_employee_role(apps, schema_editor):
    from employees.services import employee_role_ensure, employees_assign_employee_role

    employee_role_ensure()
    employees_assign_employee_role()


def unseed_employee_role(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    Role = apps.get_model("employees", "Role")
    from employees.permission_catalog import EMPLOYEE_ROLE_NAME

    role = Role.objects.filter(name=EMPLOYEE_ROLE_NAME).first()
    if role is None:
        return
    Employee.objects.filter(role=role).update(role=None)
    role.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0002_seed_permission_catalog"),
    ]

    operations = [
        migrations.RunPython(seed_employee_role, unseed_employee_role),
    ]
