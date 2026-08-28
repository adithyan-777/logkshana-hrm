from django.db import connection, migrations


def _quote(name: str) -> str:
    return connection.ops.quote_name(name)


def _schema_names(*, cursor) -> list[str]:
    cursor.execute(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('public', 'information_schema')
          AND schema_name NOT LIKE 'pg_%%'
        ORDER BY schema_name
        """
    )
    return [row[0] for row in cursor.fetchall()]


def _has_table(*, cursor, schema: str, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        [schema, table],
    )
    return cursor.fetchone() is not None


def _table_names(*, cursor, schema: str) -> list[str]:
    cursor.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = %s
          AND tablename <> 'django_migrations'
        ORDER BY tablename
        """,
        [schema],
    )
    return [row[0] for row in cursor.fetchall()]


def _employee_count(*, cursor, schema: str) -> int:
    cursor.execute(
        f"SELECT COUNT(*) FROM {_quote(schema)}.{_quote('employees_employee')}"
    )
    return cursor.fetchone()[0]


def move_tenant_tables_to_public(apps, schema_editor):
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        tenant_schemas = [
            schema
            for schema in _schema_names(cursor=cursor)
            if _has_table(cursor=cursor, schema=schema, table="employees_employee")
        ]
        if not tenant_schemas:
            return

        if not _has_table(cursor=cursor, schema="public", table="employees_employee"):
            source = max(
                tenant_schemas,
                key=lambda schema: _employee_count(cursor=cursor, schema=schema),
            )
            public_tables = set(_table_names(cursor=cursor, schema="public"))
            for table in _table_names(cursor=cursor, schema=source):
                if table in public_tables:
                    continue
                cursor.execute(
                    f"ALTER TABLE {_quote(source)}.{_quote(table)} SET SCHEMA public"
                )

        for schema in tenant_schemas:
            cursor.execute(f"DROP SCHEMA IF EXISTS {_quote(schema)} CASCADE")


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0005_remove_tenant_fields"),
        ("employees", "0003_permission_role_employee_role"),
        ("attendance", "0001_initial"),
        ("leave", "0001_initial"),
        ("schedule", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(move_tenant_tables_to_public, migrations.RunPython.noop),
    ]
