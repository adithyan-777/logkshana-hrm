"""Carry selected legacy data into the current schema.

Two steps, driven by ``carry_manifest.json`` in this directory:

* ``export`` reads the chosen tables from a scratch database (restored
  from the legacy dump beforehand) and saves them as plain JSON files
  under OUT_DIR (default ``./carry_data``) — inspectable, committable
  nowhere (git-ignored), re-loadable offline.
* ``load`` reads those JSON files and recreates the rows in the target
  tenant through the current services (validation applies), then heals
  attendance (materialize + recalc affected days) and prints a report.

Both steps are idempotent: every entity matches by natural key first
(username / emp_code / code / name / serial / external_id).

Usage (server, repo root):
  # 1. stage the dump once (postgres:18 container):
  docker run --rm -v $HOME/backups/pattika:/backups postgres:18-alpine \
    sh -c 'PGPASSWORD=$DB_PASSWORD pg_restore -h <rds> -U <user> -d <scratch> --no-owner /backups/<file>.dump'
  # 2. export selected rows to JSON:
  docker compose run --rm web python manage.py carry_legacy_data --step export \\
      --scratch-db <scratch> --out-dir ./carry_data
  # 3. load into the fresh tenant:
  docker compose run --rm -v $(pwd)/carry_data:/carry_data web python \\
      manage.py carry_legacy_data --step load --from-dir /carry_data --tenant demo
"""

import json
from datetime import date, datetime, time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils import timezone
from django_tenants.utils import schema_context

MANIFEST_NAME = "carry_manifest.json"
DEFAULT_OUT_DIR = "./carry_data"


def _jsonable(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _parse_date(value):
    return date.fromisoformat(value) if value else None


def _parse_time(value):
    return time.fromisoformat(value) if value else None


def _parse_datetime(value):
    return datetime.fromisoformat(value) if value else None


class Command(BaseCommand):
    help = (
        "Export selected legacy rows to JSON (step=export, from a scratch "
        "DB) or load them into the current schema (step=load)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--step", choices=("export", "load"), required=True)
        parser.add_argument("--manifest", default=None)
        parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
        parser.add_argument("--from-dir", default=DEFAULT_OUT_DIR)
        parser.add_argument("--scratch-db", default=None)
        parser.add_argument("--src-host", default=None)
        parser.add_argument("--src-port", default=None)
        parser.add_argument("--src-user", default=None)
        parser.add_argument("--src-password", default=None)
        parser.add_argument("--src-schema", default="demo")
        parser.add_argument("--tenant", default="demo")
        parser.add_argument("--dry-run", action="store_true")

    # ------------------------------------------------------------------
    # Entry.
    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        manifest_path = options["manifest"] or str(
            Path(__file__).with_name(MANIFEST_NAME)
        )
        with open(manifest_path) as handle:
            manifest = json.load(handle)
        self.manifest = manifest
        self.src_schema = options["src_schema"]
        self._options = options

        if options["step"] == "export":
            if not options["scratch_db"]:
                raise CommandError("--scratch-db is required for export")
            self._export(out_dir=options["out_dir"], scratch=options["scratch_db"])
        else:
            self._load(from_dir=options["from_dir"], tenant_schema=options["tenant"], dry_run=options["dry_run"])

    # ------------------------------------------------------------------
    # Export: scratch DB -> JSON files.
    # ------------------------------------------------------------------
    def _src_cursor(self, *, scratch):
        base = settings.DATABASES["default"]
        params = dict(base)
        params["NAME"] = scratch
        for key, opt in (
            ("HOST", "_opt_src_host"),
            ("PORT", "_opt_src_port"),
            ("USER", "_opt_src_user"),
            ("PASSWORD", "_opt_src_password"),
        ):
            value = getattr(self, opt, None)
            if value:
                params[key] = value
        connections.databases["carry_src"] = params
        return connections["carry_src"].cursor()

    def _export(self, *, out_dir, scratch):
        self._opt_src_host = self._options.get("src_host")
        self._opt_src_port = self._options.get("src_port")
        self._opt_src_user = self._options.get("src_user")
        self._opt_src_password = self._options.get("src_password")

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        counts = {}
        with self._src_cursor(scratch=scratch) as cursor:
            for entity in self.manifest["entities"]:
                if "table" not in entity:
                    continue  # generated (entries) or derived (users) below
                rows = self._fetch_entity(cursor, entity)
                if entity["name"] == "employees":
                    rows = self._attach_employee_users(cursor, rows)
                if entity["name"] == "assignments":
                    rows = self._attach_assignment_members(cursor, rows)
                if entity["name"] == "employees":
                    self._export_users(cursor, out, rows)
                if entity["name"] == "employees":
                    self._export_branches(cursor, out, rows)
                (out / f"{entity['name']}.json").write_text(
                    json.dumps(rows, indent=1, default=str)
                )
                counts[entity["name"]] = len(rows)
                self.stdout.write(f"  export {entity['name']}: {len(rows)}")
        (out / "counts.json").write_text(json.dumps(counts, indent=1))
        (out / "manifest.json").write_text(
            json.dumps(self.manifest, indent=1)
        )
        self.stdout.write(self.style.SUCCESS(f"Exported to {out}"))

    def _fetch_entity(self, cursor, entity):
        cols = ", ".join(entity["columns"])
        cursor.execute(
            f"SELECT {cols} FROM {self.src_schema}.{entity['table']} ORDER BY id"
            if entity["schema"] != "public"
            else f"SELECT {cols} FROM {entity['table']} ORDER BY id"
        )
        names = [desc[0] for desc in cursor.description]
        return [
            {key: _jsonable(value) for key, value in zip(names, row)}
            for row in cursor.fetchall()
        ]

    def _attach_employee_users(self, cursor, rows):
        user_ids = {row["user_id"] for row in rows if row.get("user_id")}
        users = {}
        if user_ids:
            cursor.execute(
                "SELECT id, username, email, is_active, is_staff, is_superuser, date_joined "
                "FROM users_user WHERE id = ANY(%s)",
                [list(user_ids)],
            )
            names = [desc[0] for desc in cursor.description]
            users = {
                row[0]: {key: _jsonable(value) for key, value in zip(names, row)}
                for row in cursor.fetchall()
            }
        for row in rows:
            row["user"] = users.get(row.pop("user_id"))
        return rows

    def _attach_assignment_members(self, cursor, rows):
        link = next(
            e["with_members"]
            for e in self.manifest["entities"]
            if e["name"] == "assignments"
        )
        cursor.execute(
            f"SELECT m.{link['link']}, e.emp_code FROM {self.src_schema}.{link['table']} m "
            f"JOIN {self.src_schema}.employees_employee e ON e.id = m.{link['member']} "
            "ORDER BY m.id"
        )
        members = {}
        for assignment_id, emp_code in cursor.fetchall():
            members.setdefault(assignment_id, []).append(emp_code)
        for row in rows:
            row["members"] = members.get(row["id"], [])
        return rows

    def _export_users(self, cursor, out, rows):
        users = [row["user"] for row in rows if row.get("user")]
        (out / "users.json").write_text(json.dumps(users, indent=1, default=str))
        self.stdout.write(f"  export users: {len(users)}")

    def _export_branches(self, cursor, out, rows):
        branch_ids = {row["branch_id"] for row in rows if row.get("branch_id")}
        branches = []
        if branch_ids:
            cursor.execute(
                "SELECT id, name, code FROM employees_branch WHERE id = ANY(%s) ORDER BY id",
                [list(branch_ids)],
            )
            names = [desc[0] for desc in cursor.description]
            branches = [
                {key: _jsonable(value) for key, value in zip(names, row)}
                for row in cursor.fetchall()
            ]
        (out / "branches.json").write_text(json.dumps(branches, indent=1, default=str))
        self.stdout.write(f"  export branches: {len(branches)}")

    # ------------------------------------------------------------------
    # Load: JSON files -> current schema.
    # ------------------------------------------------------------------
    def _load(self, *, from_dir, tenant_schema, dry_run):
        from companies.models import Company

        data = {}
        src = Path(from_dir)
        for name in ("users", "branches"):
            path = src / f"{name}.json"
            data[name] = json.loads(path.read_text()) if path.exists() else []
        for entity in self.manifest["entities"]:
            if "table" not in entity:
                continue  # generated (entries)
            path = src / f"{entity['name']}.json"
            if not path.exists():
                raise CommandError(f"Missing export file: {path} (run --step export first)")
            data[entity["name"]] = json.loads(path.read_text())

        company = Company.objects.filter(schema_name=tenant_schema).first()
        if company is None:
            raise CommandError(f"No company with schema '{tenant_schema}'")

        report = {}
        self._emp_map = {}

        def _run():
            with schema_context(tenant_schema):
                report.update(self._load_org(data))
                user_map = self._load_users(data, company)
                report["employees"] = self._load_employees(data, user_map)
                tt_map = self._load_timetables(data)
                report.update(self._load_schedules(data, tt_map))
                report.update(self._load_devices(data, company))
                report["punches"] = self._load_punches(data)
                report.update(self._heal_attendance(data))

        if dry_run:
            try:
                with transaction.atomic():
                    _run()
                    raise _Rollback
            except _Rollback:
                pass
            self.stdout.write(self.style.SUCCESS("Dry run OK (rolled back)"))
        else:
            with transaction.atomic():
                _run()
        for key, value in report.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("Load complete"))

    # -- org -----------------------------------------------------------
    def _load_org(self, data):
        from employees.models import Department, Position, Role

        made = {"departments": 0, "positions": 0, "roles": 0}
        for row in data.get("departments", []):
            _, created = Department.objects.get_or_create(
                code=row["code"] or row["name"],
                defaults={"name": row["name"]},
            )
            made["departments"] += created
        for row in data.get("positions", []):
            _, created = Position.objects.get_or_create(
                code=row["code"] or row["title"],
                defaults={"title": row["title"]},
            )
            made["positions"] += created
        for row in data.get("roles", []):
            _, created = Role.objects.get_or_create(
                name=row["name"], defaults={"is_system": row["is_system"]}
            )
            made["roles"] += created
        return made

    # -- users ---------------------------------------------------------
    def _load_users(self, data, company):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user_map = {}
        made = 0
        for row in data.get("users", []):
            email = (row["email"] or "").strip().lower()
            clash = (
                User.objects.filter(email__iexact=email)
                .exclude(username=row["username"])
                .first()
                if email
                else None
            )
            if clash is not None:
                raise CommandError(
                    f"Email {email} already used by '{clash.username}'; "
                    f"cannot carry user '{row['username']}'"
                )
            user, created = User.objects.get_or_create(
                username=row["username"],
                defaults={
                    "email": email,
                    "is_active": row["is_active"],
                    "is_staff": row["is_staff"],
                    "is_superuser": row["is_superuser"],
                },
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
                made += 1
            company.members.add(user)
            user_map[row["id"]] = user
        self.stdout.write(f"  users: {made} created")
        return user_map

    # -- employees -----------------------------------------------------
    def _load_employees(self, data, user_map):
        from django.db import connection

        from companies.models import Branch, Company
        from employees.models import Department, Employee, Position, Role
        from employees.services import employee_role_ensure

        dept_by_code = {d.code: d for d in Department.objects.all()}
        pos_by_code = {p.code: p for p in Position.objects.all()}
        dept_rows = {r["id"]: r for r in data.get("departments", [])}
        pos_rows = {r["id"]: r for r in data.get("positions", [])}
        role_rows = {r["id"]: r for r in data.get("roles", [])}
        made = 0
        for row in data.get("employees", []):
            existing = Employee.objects.filter(emp_code=row["emp_code"]).first()
            if existing is not None:
                self._emp_map[row["id"]] = existing
                continue
            user = None
            if row.get("user"):
                user = user_map.get(row["user"]["id"])
            branch = None
            if row.get("branch_id") is not None:
                branch_row = next(
                    (b for b in data.get("branches", []) if b["id"] == row["branch_id"]),
                    None,
                )
                if branch_row is not None:
                    branch = Branch.objects.filter(name=branch_row["name"]).first()
            if branch is None:
                from companies.services import company_primary_branch_get_or_create

                company = Company.objects.get(schema_name=connection.schema_name)
                branch, _ = company_primary_branch_get_or_create(company=company)
            department = None
            if row.get("department_id") in dept_rows:
                department = dept_by_code.get(dept_rows[row["department_id"]]["code"])
            position = None
            if row.get("position_id") in pos_rows:
                position = pos_by_code.get(pos_rows[row["position_id"]]["code"])
            role = None
            if row.get("role_id") in role_rows:
                role = Role.objects.filter(name=role_rows[row["role_id"]]["name"]).first()
            employee = Employee(
                user=user,
                first_name=row["first_name"],
                last_name=row["last_name"],
                emp_code=row["emp_code"] or None,
                department=department,
                position=position,
                branch=branch,
                email=(row["email"] or "").strip().lower(),
                mobile=row["mobile"] or "",
                hire_date=_parse_date(row["hire_date"]),
                is_active=row["is_active"],
                role=role or employee_role_ensure(),
            )
            employee.full_clean()
            employee.save()
            self._emp_map[row["id"]] = employee
            made += 1
        return made

    @staticmethod
    def _by_old_id(objects_by_code, rows, old_id, code_field):
        if old_id is None:
            return None
        match = next((r for r in rows if r["id"] == old_id), None)
        if match is None:
            return None
        return objects_by_code.get(match.get(code_field))

    # -- timetables ----------------------------------------------------
    def _load_timetables(self, data):
        from schedule.services import timetable_break_create, timetable_create

        tt_map = {}
        made = {"timetables": 0, "breaks": 0}
        timetables = {row["id"]: row for row in data.get("timetables", [])}
        breaks = {}
        for row in data.get("breaks", []):
            breaks.setdefault(row["timetable_id"], []).append(row)
        for old_id, row in timetables.items():
            from schedule.models import Timetable

            existing = Timetable.objects.filter(code=row["code"]).first()
            if existing is not None:
                tt_map[old_id] = existing
                continue
            timetable = timetable_create(
                name=row["name"],
                code=row["code"],
                type=row["type"],
                check_in=_parse_time(row["check_in"]),
                check_out=_parse_time(row["check_out"]),
                check_out_cross_days=row["check_out_cross_days"] or 0,
                day_change_time=_parse_time(row.get("day_change_time")),
                work_minutes=row["work_minutes"],
                grace_period_check_out=row["grace_period_check_out"],
                grace_period_minutes=row["grace_period_minutes"] or 0,
                count_break_time_as_work_time=row["count_break_time_as_work_time"],
                multiple_in_out=row["multiple_in_out"],
                is_active=row["is_active"],
            )
            for brow in breaks.get(old_id, []):
                timetable_break_create(
                    timetable=timetable,
                    name=brow["name"],
                    break_time_type=brow["break_time_type"],
                    break_time_minutes=brow["break_time_minutes"],
                    start_time=_parse_time(brow["start_time"]),
                    end_time=_parse_time(brow["end_time"]),
                )
                made["breaks"] += 1
            tt_map[old_id] = timetable
            made["timetables"] += 1
        for key, value in made.items():
            self.stdout.write(f"  {key}: {value}")
        return tt_map

    # -- schedules -----------------------------------------------------
    def _load_schedules(self, data, tt_map):
        from schedule.models import EmployeeScheduleAssignment, Schedule, ScheduleEntry
        from schedule.services import assignment_create, schedule_create

        made = {"schedules": 0, "entries": 0, "assignments": 0}
        sched_map = {}
        emp_by_code = {}
        for row in data.get("employees", []):
            if row["id"] in self._emp_map:
                emp_by_code[row["emp_code"]] = self._emp_map[row["id"]]
        for row in data.get("schedules", []):
            timetable = tt_map.get(row["timetable_id"])
            if timetable is None:
                raise CommandError(f"Schedule '{row['name']}' references missing timetable {row['timetable_id']}")
            schedule = Schedule.objects.filter(name=row["name"]).first()
            if schedule is None:
                schedule = schedule_create(
                    name=row["name"],
                    timetable=timetable,
                    start_date=_parse_date(row["start_date"]),
                    end_date=_parse_date(row["end_date"]),
                    repeat=row["repeat"],
                    repeat_every=row["repeat_every"] or 1,
                    repeat_unit=row["repeat_unit"],
                )
                made["schedules"] += 1
            for day_index in range(7):
                _, created = ScheduleEntry.objects.get_or_create(
                    schedule=schedule,
                    day_index=day_index,
                    defaults={"timetable": timetable},
                )
                made["entries"] += created
            sched_map[row["id"]] = schedule
        for row in data.get("assignments", []):
            schedule = sched_map.get(row["schedule_id"])
            if schedule is None:
                continue
            members = [
                emp_by_code[code] for code in row.get("members", []) if code in emp_by_code
            ]
            existing = EmployeeScheduleAssignment.objects.filter(
                schedule=schedule, start_date=_parse_date(row["start_date"])
            ).first()
            if existing is None:
                assignment_create(
                    schedule=schedule,
                    employees=members,
                    start_date=_parse_date(row["start_date"]),
                    end_date=_parse_date(row["end_date"]),
                    priority=row["priority"] or 0,
                    name=row["name"] or "",
                )
                made["assignments"] += 1
            else:
                existing.employees.add(*members)
        for key, value in made.items():
            self.stdout.write(f"  {key}: {value}")
        return made

    # -- devices -------------------------------------------------------
    def _load_devices(self, data, company):
        from companies.models import Branch, Device, DeviceBrand, DeviceType

        made = {"devices": 0}
        for row in data.get("devices", []):
            if Device.objects.filter(serial_number=row["serial_number"]).exists():
                continue
            dtype = None
            # device_type resolved from exported device_types by old id
            type_row = next(
                (t for t in data.get("device_types", []) if t["id"] == row.get("device_type_id")),
                None,
            )
            if type_row is not None:
                brand_row = next(
                    (b for b in data.get("device_brands", []) if b["id"] == type_row["brand_id"]),
                    {"name": "Unknown"},
                )
                brand, _ = DeviceBrand.objects.get_or_create(
                    name=brand_row["name"],
                    defaults={"description": brand_row.get("description") or "", "is_active": True},
                )
                dtype, _ = DeviceType.objects.get_or_create(
                    brand=brand,
                    model_name=type_row["model_name"],
                    defaults={"description": type_row.get("description") or "", "is_active": True},
                )
            branch = Branch.objects.filter(company=company).order_by("id").first()
            device = Device(
                serial_number=row["serial_number"],
                name=row["name"] or "",
                company=company,
                branch=branch,
                device_type=dtype,
                is_active=row["is_active"],
                last_gateway_log_id=row["last_gateway_log_id"] or 0,
                last_synced_at=_parse_datetime(row["last_synced_at"]),
                last_sync_error=row["last_sync_error"] or "",
            )
            device.full_clean()
            device.save()
            made["devices"] += 1
        for key, value in made.items():
            self.stdout.write(f"  {key}: {value}")
        return made

    # -- punches -------------------------------------------------------
    def _load_punches(self, data):
        from attendance.models import AttendanceActivity

        emp_map = self._emp_map
        made = 0
        for row in data.get("punches", []):
            employee = emp_map.get(row["employee_id"])
            if employee is None:
                continue
            existing = None
            if row.get("external_id"):
                existing = AttendanceActivity.objects.filter(
                    external_id=row["external_id"]
                ).first()
            if existing is None:
                existing = AttendanceActivity.objects.filter(
                    employee=employee, punch_time=_parse_datetime(row["punch_time"])
                ).first()
            if existing is not None:
                continue
            punch = AttendanceActivity(
                employee=employee,
                punch_time=_parse_datetime(row["punch_time"]),
                direction=row["direction"],
                method=row["method"],
                external_id=row["external_id"] or "",
                raw_data=row["raw_data"] or {},
            )
            punch.full_clean()
            punch.save()
            made += 1
        return made

    # -- heal + verify -------------------------------------------------
    def _heal_attendance(self, data):
        from attendance.recalculation import recalculate_attendance

        days = {}
        for row in data.get("punches", []):
            employee = self._emp_map.get(row["employee_id"])
            if employee is None:
                continue
            day = _parse_datetime(row["punch_time"])
            if day is None:
                continue
            days.setdefault(employee.pk, set()).add(timezone.localtime(day).date())
        healed = 0
        from employees.models import Employee

        for employee_pk, day_set in days.items():
            employee = Employee.objects.filter(pk=employee_pk).first()
            if employee is None:
                continue
            for day in sorted(day_set):
                if recalculate_attendance(employee=employee, day=day) is not None:
                    healed += 1
        from attendance.models import AttendanceActivity

        unlinked = AttendanceActivity.objects.filter(scheduled_shift__isnull=True).count()
        self.stdout.write(f"  days recalculated: {healed}")
        self.stdout.write(f"  unlinked punches: {unlinked}")
        return {"days_healed": healed, "unlinked_punches": unlinked}


class _Rollback(Exception):
    pass
