# Logkshana — Frontend Handoff

Reference for styling the Django server-rendered UI.

**App name:** Logkshana  
**Stack:** Django templates, HTMX 2.0.4, **jQuery DataTables**, vanilla JS, `static/css/app.css`  
**Auth:** django-allauth

**Quick jump:** [CSS handoff guide](#css-handoff-guide) · [Layout & CSS classes](#layout--css-classes) · [Forms reference](#forms-reference) · [Nice to haves](#nice-to-haves) · [Site map](#site-map) · [DataTables integration](#datatables-integration) · [Tables reference](#tables-reference)

---

## CSS handoff guide

What a frontend dev needs to get started. Detailed table column specs and DataTables config are in [DataTables integration](#datatables-integration) and [Tables reference](#tables-reference) at the end of this document.

### Must have — structure & hooks

| Detail | Why | Where |
|--------|-----|-------|
| Page inventory | Know every screen | [Site map](#site-map) |
| Layout structure | Sidebar + header + content vs standalone login | `templates/layouts/app_shell.html`, `base.html` |
| CSS class names | Templates already use these — style them, don't rename | `static/css/app.css`, [Key CSS classes](#key-css-classes) |
| Table headers & column count | Column widths, sort types, `data-order` attrs | [Tables reference](#tables-reference), [DataTables integration](#datatables-integration) |
| Form fields & labels | Input sizing, grids, required markers | [Forms reference](#forms-reference) |
| Component variants | Badges, messages, empty states | `.badge`, `.message`, `.empty-state` |
| DataTables UI | Length filter, search, paginate controls | `.dataTables_wrapper` and children |

### Must have — behavior & constraints

| Detail | Notes |
|--------|-------|
| **DataTables on all data tables** | 21 read-only tables use DataTables — see [DataTables integration](#datatables-integration). Replaces list `.search-input` and `.pagination`. |
| **HTMX partial updates** | List containers still swap via HTMX after add forms. **Destroy + re-init** DataTable after each swap. Keep stable list container IDs. |
| **Backend page size** | Django paginates **25 rows** per request today. Client-side DT only sees current page unless server-side DT is added. |
| **Responsive breakpoint** | Mobile sidebar drawer at **max-width 900px**. DataTables **Responsive** extension for table columns. |
| **Two layout modes** | `body.app-body` (full app) vs `body.standalone-page` (login, centered max 960px). |
| **Sticky header** | `.app-header` is sticky. Use **FixedHeader** extension for table `<thead>`, not the app header. |
| **Wide report tables** | Up to 10 columns — FixedHeader + horizontal scroll in `.dataTables_wrapper` |
| **Sidebar width** | Fixed **240px** on desktop; slides in as overlay on mobile. |

### Should have — visual system (decisions needed)

There is no formal design system yet — only functional CSS. Decide or inherit defaults for:

| Token | Current value | Dev should define |
|-------|---------------|-------------------|
| Primary | `#1d4ed8` | Brand primary + hover (`#1e40af`) |
| Text | `#111827` | Body, muted (`#6b7280`), labels (`#4b5563`) |
| Background | `#f9fafb` | Page bg, card bg (`#fff`), sidebar (`#111827`) |
| Borders | `#e5e7eb` | Dividers, inputs, cards |
| Font | `system-ui, sans-serif` | Family + scale (h1 1.25rem, badges 0.75rem, etc.) |
| Radius | `0.375rem` / `0.5rem` | Consistent radius tokens |
| Spacing | Ad hoc | Scale (4 / 8 / 12 / 16 / 24px…) |
| Shadows | Almost none | Cards, dropdowns, elevated panels |
| Focus rings | Not styled | Keyboard accessibility on all interactive elements |

Suggested approach: define CSS variables in `:root` at the top of `app.css` and refactor hardcoded values to use them.

### Should have — states & edge cases

Style these explicitly — they appear on many pages:

| State | Class / element | Pages |
|-------|-----------------|-------|
| Empty table | `.empty-state` | All list + report pages |
| Field validation | `.error` on field, `.message.error` on form | All add forms |
| Success after submit | `.message.success` | All HTMX add forms |
| Active nav link | `.sidebar-link.is-active` | Sidebar |
| Alert KPI | `.kpi-card-alert` | Dashboard pending counts |
| Disabled pagination | `.pagination-disabled` | Legacy — remove when DT replaces `.pagination` |
| Missing badge CSS | `.status-early_out`, `.status-auto_approved`, etc. | Daily attendance, overtime reports |
| Collapsed sidebar group | `.sidebar-group[open]` | Leave, Schedule, Reports nav |
| Mobile overlay | `.sidebar-overlay` + `[hidden]` | ≤900px viewport |

### Handoff checklist (give the dev)

- [ ] This document (`docs/frontend-handoff.md`)
- [ ] Running app access (or screenshots of each page type)
- [ ] Brand inputs — logo, colors, font (optional; defaults exist)
- [ ] Target devices — desktop-first vs mobile-first
- [ ] Design reference — Figma/mockup if available
- [ ] Scope — DataTables client-side (Phase 1) vs server-side JSON APIs (Phase 2)
- [ ] Backend coordination — add `id` + `.datatable` to tables, `data-order` on badge/num cells

### Suggested CSS build order

1. CSS variables / design tokens in `:root`
2. App shell — sidebar, header, breadcrumbs, mobile drawer
3. Typography + base element styles
4. Buttons (`.btn`, `.btn-primary`) + form inputs (`.field`, `.field-row`)
5. **DataTables** — base CSS + `datatables-overrides.css`; init helper; per-table config from [Tables reference](#tables-reference)
6. Badges + messages + empty states (badges render inside DT cells)
7. Form sections (`.form-section`) + formset table (not DT)
8. Report filters (`.report-filters`) — keep above DT result tables
9. Dashboard KPI cards
10. Login page + Django flash messages
11. Nice-to-haves (see below)

### What the dev does NOT need

- Django/Python business logic
- REST API contracts (server-rendered HTML only)
- Database schema (field types are in [Forms reference](#forms-reference))

---

## Layout & CSS classes

### Page modes

| Mode | Body class | Used for |
|------|------------|----------|
| App shell | `app-body` | All authenticated pages |
| Standalone | `standalone-page` | Login only |

### App shell structure

```
.app-layout
  .sidebar          ← dark nav, 240px
  .app-main
    .app-header     ← sticky: toggle, breadcrumbs, h1, .btn-primary, username
    .app-content    ← max-width 1200px, page body
```

### Key CSS classes

| Class | Purpose |
|-------|---------|
| `.employee-table`, `.data-table`, `.datatable` | Data tables (DT init on `.datatable`) |
| `.formset-table` | Inline formset only — **no DataTables** |
| `.field`, `.field-row`, `.field.checkbox` | Form layout |
| `.form-section` | Fieldset card with legend |
| `.search-input` | **Deprecated** on list pages when DT search is active |
| `.report-filters` | Report filter panel (keep — separate from DT search) |
| `.badge`, `.badge.status-*` | Status pills inside table cells |
| `.message.success`, `.message.error` | Form feedback |
| `.empty-state` | No results (when table not rendered) |
| `.pagination` | **Deprecated** when DataTables pagination is active |
| `.dataTables_wrapper`, `.dataTables_filter`, etc. | DataTables injected UI |
| `.dashboard-kpis`, `.kpi-card` | Dashboard metrics |
| `.btn.btn-primary` | Header action button |

### Badge modifiers in use

`.active`, `.inactive`, `.status-draft`, `.status-pending`, `.status-approved`, `.status-rejected`, `.status-cancelled`, `.status-present`, `.status-absent`, `.status-late`, `.status-incomplete`, `.status-leave`

Additional attendance statuses in data but **no CSS yet:** `early_out`, `day_off`, `holiday`, `overtime`, `worked_holiday`, `auto_approved`

### Current color palette (from `app.css`)

| Role | Hex |
|------|-----|
| Primary / active link | `#1d4ed8` |
| Primary hover | `#1e40af` |
| Body text | `#111827` |
| Muted text | `#6b7280` |
| Label text | `#4b5563` |
| Page background | `#f9fafb` |
| Card / table bg | `#ffffff` |
| Border | `#e5e7eb` |
| Sidebar bg | `#111827` |
| Sidebar text | `#d1d5db` / `#e5e7eb` |
| Success bg / text | `#dcfce7` / `#166534` |
| Error bg / text | `#fee2e2` / `#991b1b` |
| Warning badge bg / text | `#fef3c7` / `#92400e` |
| Alert KPI border / bg | `#fcd34d` / `#fffbeb` |
| Overlay | `rgba(17, 24, 39, 0.45)` |

### HTMX swap targets (do not remove or rename)

| Page | List container | Form container | Refresh event |
|------|----------------|----------------|---------------|
| Employees | `#employee-list` | `#employee-form-container` | `employeeCreated` |
| Punches | `#transaction-list` | `#transaction-form-container` | `attendanceTransactionCreated` |
| Daily | `#daily-list` | `#daily-form-container` | `dailyAttendanceCreated` |
| Corrections | `#correction-list` | `#correction-form-container` | `attendanceCorrectionCreated` |
| Rules | `#rule-list` | `#rule-form-container` | `attendanceRuleCreated` |
| Leave types | `#leave-type-list` | `#leave-type-form-container` | `leaveTypeCreated` |
| Leave policies | `#leave-policy-list` | `#leave-policy-form-container` | `leavePolicyCreated` |
| Leave requests | `#leave-request-list` | `#leave-request-form-container` | `leaveRequestCreated` |
| Holidays | `#holiday-list` | `#holiday-form-container` | `holidayCreated` |
| Timetables | `#timetable-list` | `#timetable-form-container` | `timetableCreated` |
| Shifts | `#shift-list` | `#shift-form-container` | `shiftCreated` |
| Assignments | `#assignment-list` | `#assignment-form-container` | `assignmentCreated` |
| Temporary | `#temporary-list` | `#temporary-form-container` | `temporaryCreated` |

Pagination in HTMX mode uses `hx-target` pointing at the list container — **will be removed** when DataTables replaces server pagination. Until migration is complete, destroy DT before HTMX swap and re-init after.

Style `htmx-request` on list targets for loading feedback during refresh.

---

## Forms reference

Every form in the app. **Label** is the exact text shown to the user in the template. **Field name** is the Django form field / HTML `name` attribute.

Form CSS: fields use `.field`, checkboxes use `.field.checkbox`, grouped sections use `.form-section` with `<legend>`, side-by-side fields use `.field-row`.

---

### Login

| | |
|---|---|
| **Page URL** | `/accounts/login/` |
| **Template** | `templates/account/login.html` |
| **Layout** | Standalone (no sidebar) |
| **Submit button** | "Sign In" |
| **Note** | Rendered via django-allauth `{{ form.as_p }}` — typically Login, Password, Remember me |

---

### Profile (read-only, not a form)

| | |
|---|---|
| **Page URL** | `/accounts/profile/` |
| **Template** | `templates/account/profile.html` |
| **Display fields** | Username, Email (if set) — rendered as `<dl class="profile-details">` |

---

### Add employee

| | |
|---|---|
| **Page URL** | `/employees/add/` |
| **Template** | `templates/employees/partials/employee_form.html` |
| **Form ID** | `#employee-form` |
| **Submit button** | "Add Employee" |
| **HTMX** | Posts to same URL; replaces `#employee-form-container` |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | First name * | `first_name` | text | Yes |
| 2 | Last name | `last_name` | text | No |
| 3 | Employee code | `emp_code` | text | No |
| 4 | Department | `department` | select | No |
| 5 | Position | `position` | select | No |
| 6 | Email | `email` | email | No |
| 7 | Mobile | `mobile` | text | No |
| 8 | Hire date | `hire_date` | date | No |
| 9 | Active | `is_active` | checkbox | No |

**Success state:** `.invite-box` with password-setup link, Copy button, "Add another employee" link.

---

### Record punch

| | |
|---|---|
| **Page URL** | `/attendance/transactions/add/` |
| **Template** | `templates/attendance/partials/transaction_form.html` |
| **Form ID** | `#transaction-form` |
| **Submit button** | "Record Punch" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Employee * | `employee` | select | Yes |
| 2 | Timestamp * | `timestamp` | datetime-local | Yes |
| 3 | Direction | `direction` | select | No |
| 4 | Source | `source` | select | No |
| 5 | External ID * | `external_id` | text | Yes |
| 6 | External employee ID | `external_employee_id` | text | No |

**Direction options:** Check In, Check Out, Unknown  
**Source options:** Biometric, Web, Mobile, Manual, Import

---

### Add daily attendance record

| | |
|---|---|
| **Page URL** | `/attendance/daily/add/` |
| **Template** | `templates/attendance/partials/daily_form.html` |
| **Form ID** | `#daily-form` |
| **Submit button** | "Add Daily Record" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Employee * | `employee` | select | Yes |
| 2 | Date * | `date` | date | Yes |
| 3 | Status | `status` | select | No |
| 4 | Shift | `shift` | select | No |
| 5 | Timetable | `timetable` | select | No |
| 6 | Scheduled minutes | `scheduled_minutes` | number | No |
| 7 | Worked minutes | `worked_minutes` | number | No |
| 8 | Late minutes | `late_minutes` | number | No |
| 9 | Early leave minutes | `early_leave_minutes` | number | No |
| 10 | Overtime minutes | `overtime_minutes` | number | No |
| 11 | Has check in | `has_check_in` | checkbox | No |
| 12 | Has check out | `has_check_out` | checkbox | No |
| 13 | Notes | `notes` | textarea | No |

**Status options:** Present, Absent, Late, Early Out, Incomplete, Day Off, Holiday, Leave, Worked Holiday, Overtime

---

### Submit attendance correction

| | |
|---|---|
| **Page URL** | `/attendance/corrections/add/` |
| **Template** | `templates/attendance/partials/correction_form.html` |
| **Form ID** | `#correction-form` |
| **Submit button** | "Submit Correction" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Employee * | `employee` | select | Yes |
| 2 | Date * | `date` | date | Yes |
| 3 | Status | `status` | select | No |
| 4 | Check in | `check_in` | datetime-local | No |
| 5 | Check out | `check_out` | datetime-local | No |
| 6 | Reason * | `reason` | textarea | Yes |

**Status options:** Pending, Approved, Rejected, Cancelled

---

### Add attendance rule

| | |
|---|---|
| **Page URL** | `/attendance/rules/add/` |
| **Template** | `templates/attendance/partials/rule_form.html` |
| **Form ID** | `#rule-form` |
| **Submit button** | "Add Rule" |

| # | Label | Field name | Input type | Required | Section |
|---|-------|------------|------------|----------|---------|
| 1 | Name * | `name` | text | Yes | — |
| 2 | Require check in | `require_check_in` | checkbox | No | Punch requirements |
| 3 | Require check out | `require_check_out` | checkbox | No | Punch requirements |
| 4 | Allow multiple in/out | `allow_multiple_in_out` | checkbox | No | Punch requirements |
| 5 | Missing check-in = absence | `missing_check_in_as_absence` | checkbox | No | Punch requirements |
| 6 | Missing check-out = incomplete | `missing_check_out_as_incomplete` | checkbox | No | Punch requirements |
| 7 | Late grace (min) | `late_grace_minutes` | number | No | Grace periods |
| 8 | Early leave grace (min) | `early_leave_grace_minutes` | number | No | Grace periods |
| 9 | Late to absence (min) | `late_to_absence_minutes` | number | No | Grace periods |
| 10 | Duplicate punch window (min) | `duplicate_punch_window_minutes` | number | No | Grace periods |
| 11 | Active | `is_active` | checkbox | No | — |

---

### Add leave type

| | |
|---|---|
| **Page URL** | `/leave/types/add/` |
| **Template** | `templates/leave/partials/leave_type_form.html` |
| **Form ID** | `#leave-type-form` |
| **Submit button** | "Add Leave Type" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Name * | `name` | text | Yes |
| 2 | Code * | `code` | text | Yes |
| 3 | Description | `description` | textarea | No |
| 4 | Paid leave | `paid` | checkbox | No |
| 5 | Requires approval | `requires_approval` | checkbox | No |
| 6 | Allow half day | `allow_half_day` | checkbox | No |
| 7 | Allow negative balance | `allow_negative_balance` | checkbox | No |
| 8 | Active | `is_active` | checkbox | No |

---

### Add leave policy

| | |
|---|---|
| **Page URL** | `/leave/policies/add/` |
| **Template** | `templates/leave/partials/leave_policy_form.html` |
| **Form ID** | `#leave-policy-form` |
| **Submit button** | "Add Leave Policy" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Leave type * | `leave_type` | select | Yes |
| 2 | Policy name * | `name` | text | Yes |
| 3 | Entitlement days | `entitlement_days` | number | No |
| 4 | Accrual type | `accrual_type` | select | No |
| 5 | Accrual days | `accrual_days` | number | No |
| 6 | Carry forward | `carry_forward` | checkbox | No |
| 7 | Max carry forward days | `max_carry_forward_days` | number | No |
| 8 | Minimum service days | `minimum_service_days` | number | No |
| 9 | Expiry enabled | `expiry_enabled` | checkbox | No |
| 10 | Expiry days | `expiry_days` | number | No |
| 11 | Active | `is_active` | checkbox | No |

**Accrual type options:** Yearly, Monthly, No Accrual

---

### Add leave request

| | |
|---|---|
| **Page URL** | `/leave/requests/add/` |
| **Template** | `templates/leave/partials/leave_request_form.html` |
| **Form ID** | `#leave-request-form` |
| **Submit button** | "Add Leave Request" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Employee * | `employee` | select | Yes |
| 2 | Leave type * | `leave_type` | select | Yes |
| 3 | Start date * | `start_date` | date | Yes |
| 4 | End date * | `end_date` | date | Yes |
| 5 | Days * | `days` | number | Yes |
| 6 | Duration type | `duration_type` | select | No |
| 7 | Status | `status` | select | No |
| 8 | Start half day | `start_half` | checkbox | No |
| 9 | End half day | `end_half` | checkbox | No |
| 10 | Reason | `reason` | textarea | No |

**Duration type options:** Full Day, Half Day, Hourly  
**Status options:** Draft, Pending, Approved, Rejected, Cancelled

---

### Add holiday

| | |
|---|---|
| **Page URL** | `/leave/holidays/add/` |
| **Template** | `templates/leave/partials/holiday_form.html` |
| **Form ID** | `#holiday-form` |
| **Submit button** | "Add Holiday" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Name * | `name` | text | Yes |
| 2 | Date * | `date` | date | Yes |
| 3 | End date | `end_date` | date | No |
| 4 | Type | `holiday_type` | select | No |
| 5 | Description | `description` | textarea | No |
| 6 | Active | `is_active` | checkbox | No |

**Type options:** Public Holiday, Company Holiday, Optional Holiday

---

### Add timetable

| | |
|---|---|
| **Page URL** | `/schedule/timetables/add/` |
| **Template** | `templates/schedule/partials/timetable_form.html` |
| **Form ID** | `#timetable-form` |
| **Submit button** | "Add Timetable" |

| # | Label | Field name | Input type | Required | Section |
|---|-------|------------|------------|----------|---------|
| 1 | Name * | `name` | text | Yes | Basic info |
| 2 | Code * | `code` | text | Yes | Basic info |
| 3 | Type | `type` | select | No | Basic info |
| 4 | Work type | `work_type` | select | No | Basic info |
| 5 | Workday | `workday` | number | No | Basic info |
| 6 | Color | `color` | text | No | Basic info |
| 7 | Check in | `check_in` | time | No | Working hours |
| 8 | Check out | `check_out` | time | No | Working hours |
| 9 | Work minutes (flexible) | `work_minutes` | number | No | Working hours |
| 10 | Check-in window start | `check_in_start` | time | No | Working hours |
| 11 | Check-in window end | `check_in_end` | time | No | Working hours |
| 12 | Check-out window start | `check_out_start` | time | No | Working hours |
| 13 | Check-out window end | `check_out_end` | time | No | Working hours |
| 14 | Check-in cross days | `check_in_cross_days` | number | No | Working hours |
| 15 | Check-out cross days | `check_out_cross_days` | number | No | Working hours |
| 16 | Day change time | `day_change_time` | time | No | Working hours |
| 17 | Require check in | `require_check_in` | checkbox | No | Attendance rules |
| 18 | Require check out | `require_check_out` | checkbox | No | Attendance rules |
| 19 | Multiple in/out | `multiple_in_out` | checkbox | No | Attendance rules |
| 20 | Allow late in | `allow_late_in` | checkbox | No | Attendance rules |
| 21 | Late-in grace (min) | `late_in_grace_minutes` | number | No | Attendance rules |
| 22 | Allow early out | `allow_early_out` | checkbox | No | Attendance rules |
| 23 | Early-out grace (min) | `early_out_grace_minutes` | number | No | Attendance rules |
| 24 | Active | `is_active` | checkbox | No | Attendance rules |

**Type options:** Normal, Flexible  
**Work type options:** Work, Day Off, Overtime

---

### Add shift

| | |
|---|---|
| **Page URL** | `/schedule/shifts/add/` |
| **Template** | `templates/schedule/partials/shift_form.html` |
| **Form ID** | `#shift-form` |
| **Submit button** | "Add Shift" |

| # | Label | Field name | Input type | Required | Section |
|---|-------|------------|------------|----------|---------|
| 1 | Name * | `name` | text | Yes | Shift details |
| 2 | Code * | `code` | text | Yes | Shift details |
| 3 | Cycle unit | `cycle_unit` | select | No | Shift details |
| 4 | Cycle count | `cycle_count` | number | No | Shift details |
| 5 | Auto shift | `auto_shift` | checkbox | No | Shift details |
| 6 | Active | `is_active` | checkbox | No | Shift details |
| 7 | Day # | `days-N-day_number` | number | No | Cycle days (formset) |
| 8 | Timetable | `days-N-timetable` | select | No | Cycle days (formset) |
| 9 | Remove | `days-N-DELETE` | checkbox | No | Cycle days (formset) |

**Cycle unit options:** Day, Week, Month  
See [Shift formset table](#shift-formset-table-inside-add-shift-form) for inline table headers.

---

### Add schedule assignment

| | |
|---|---|
| **Page URL** | `/schedule/assignments/add/` |
| **Template** | `templates/schedule/partials/assignment_form.html` |
| **Form ID** | `#assignment-form` |
| **Submit button** | "Add Assignment" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Assignment type * | `assignment_type` | select | Yes |
| 2 | Shift * | `shift` | select | Yes |
| 3 | Start date * | `start_date` | date | Yes |
| 4 | End date * | `end_date` | date | Yes |
| 5 | Employee | `employee` | select | Conditional |
| 6 | Department | `department` | select | Conditional |
| 7 | Overwrite existing schedules | `overwrite_existing` | checkbox | No |

**Assignment type options:** Employee, Department, Group  
Employee required when type = Employee; Department required when type = Department.

---

### Add temporary schedule

| | |
|---|---|
| **Page URL** | `/schedule/temporary/add/` |
| **Template** | `templates/schedule/partials/temporary_form.html` |
| **Form ID** | `#temporary-form` |
| **Submit button** | "Add Temporary Schedule" |

| # | Label | Field name | Input type | Required |
|---|-------|------------|------------|----------|
| 1 | Employee * | `employee` | select | Yes |
| 2 | Date * | `date` | date | Yes |
| 3 | Timetable * | `timetable` | select | Yes |
| 4 | Reason | `reason` | textarea | No |
| 5 | Overrides normal schedule | `overrides_normal_schedule` | checkbox | No |

---

### Report filter forms

All report pages use `templates/reports/partials/filter_form.html` (class `.report-filters`). Submit button: **"Apply filters"**. Below the form: export links (Download CSV, Download Excel, Download PDF).

#### Standard date-range filter (Attendance summary, Department, Exceptions, Punch log)

| # | Label | Field name | Input type |
|---|-------|------------|------------|
| 1 | Date from | `date_from` | date |
| 2 | Date to | `date_to` | date |
| 3 | Department | `department` | select (empty = "All departments") |
| 4 | Employee | `employee` | select (empty = "All employees") |

#### Individual attendance filter

Same as above, but employee empty label is **"Select employee"**.

#### Exceptions filter (adds one field)

| # | Label | Field name | Input type |
|---|-------|------------|------------|
| 5 | Exception type | `exception_type` | select |

**Exception type options:** All exceptions, Late, Absent, Incomplete, Missing punch

#### Overtime filter (adds one field)

| # | Label | Field name | Input type |
|---|-------|------------|------------|
| 5 | Status | `status` | select |

**Status options:** All statuses, Pending, Approved, Rejected, Auto approved

#### Leave report filter

| # | Label | Field name | Input type |
|---|-------|------------|------------|
| 1 | Report type | `report_type` | select |
| 2 | Date from | `date_from` | date |
| 3 | Date to | `date_to` | date |
| 4 | Department | `department` | select |
| 5 | Employee | `employee` | select |
| 6 | Year | `year` | number |

**Report type options:** Leave balance, Leave utilization, Pending leave

---

### List page search inputs — replaced by DataTables

When DataTables is active, **remove or hide** these — DT provides its own `.dataTables_filter` search:

| Page | Input ID | Was used for |
|------|----------|--------------|
| Employees | `#employee-search` | HTMX server search |
| Punches | `#transaction-search` | HTMX server search |
| Daily | `#daily-search` | HTMX server search |
| Corrections | `#correction-search` | HTMX server search |
| Rules | `#rule-search` | HTMX server search |
| Leave types | `#leave-type-search` | HTMX server search |
| Leave policies | `#leave-policy-search` | HTMX server search |
| Leave requests | `#leave-request-search` | HTMX server search |
| Holidays | `#holiday-search` | HTMX server search |
| Timetables | `#timetable-search` | HTMX server search |
| Shifts | `#shift-search` | HTMX server search |
| Assignments | `#assignment-search` | HTMX server search |
| Temporary | `#temporary-search` | HTMX server search |

Until server-side DataTables is built, client-side search only filters the **current page** (≤25 rows).

---

## Nice to haves

Polish items — not required for MVP styling but improve UX. Several have minimal or no CSS today.

### Login page

| | |
|---|---|
| **URL** | `/accounts/login/` |
| **Template** | `templates/account/login.html` |
| **Issue** | Uses django-allauth `{{ form.as_p }}` — unstyled paragraph layout |
| **Nice to have** | Centered card, branded header, styled inputs matching `.field` pattern, "Forgot password?" link styling |

### Django flash messages

| | |
|---|---|
| **Template** | `templates/base.html` |
| **Issue** | Messages render as bare `<p>{{ message }}</p>` with no class |
| **Nice to have** | Toast or banner using `.message.success` / `.message.error`; dismiss button; fixed position top of content |

### HTMX loading states

| | |
|---|---|
| **Issue** | Table/form swaps have no visual feedback during request |
| **Nice to have** | Opacity fade on swap target, skeleton rows, or spinner overlay on `#employee-list` etc. Can use HTMX `htmx-request` class on body or target. |

### Employee invite box

| | |
|---|---|
| **Template** | `templates/employees/partials/employee_invite.html` |
| **Class** | `.invite-box` (minimal styling) |
| **Nice to have** | Card layout, monospace/code block for link, styled Copy button, success icon |

### Export buttons

| | |
|---|---|
| **Class** | `.export-buttons` |
| **Current** | Plain text links: Download CSV, Excel, PDF |
| **Nice to have** | DataTables **Buttons** extension as alternative/complement; secondary `.btn` variant |

### DataTables enhancements

| Enhancement | Notes |
|-------------|-------|
| Server-side processing | JSON API per table — full search/sort across all records |
| Buttons extension | CSV / Excel / PDF export from DT toolbar on reports |
| Row hover | Style `table.dataTable tbody tr:hover` |
| State saving | `stateSave: true` — remember page length, sort, search per table |
| Column visibility | ColVis button for wide report tables |
| Processing indicator | `processing: true` during server-side AJAX |

### Report hub links

| | |
|---|---|
| **Class** | `.report-link-list` |
| **Current** | Basic bordered cards |
| **Nice to have** | Icons per report type, description subtext, grid layout on wide screens |

### Table enhancements (legacy — prefer DataTables)

Most table UX (sort, search, paginate, responsive) is handled by DataTables. Remaining custom work:

| Enhancement | Notes |
|-------------|-------|
| Custom DT theme | Match app tokens in `datatables-overrides.css` |
| Badge rendering in cells | Ensure `.badge` styles work inside `table.dataTable td` |
| Print stylesheet | `@media print` on `.dataTables_wrapper` — hide controls, show all rows |

### Form enhancements

| Enhancement | Applies to |
|-------------|------------|
| Focus ring on inputs | All `.field input/select/textarea` |
| Disabled submit while posting | HTMX forms — `htmx-request` on button |
| Inline required indicator style | Fields marked `*` in labels |
| Section collapse | Long forms (Timetable, Shift) — accordion on `.form-section` |
| Date/time picker styling | Native `date`, `time`, `datetime-local` inputs |

### Sidebar enhancements

| Enhancement | Notes |
|-------------|-------|
| Icon-only collapsed mode | Planned in ui-shell-plan — 240px → 64px + localStorage |
| Badge counts on nav items | Pending leave, corrections (not implemented) |
| User avatar in footer | Replace plain username in header |

### Dashboard enhancements

| Enhancement | Notes |
|-------------|-------|
| Sparklines or trend arrows on KPIs | Not in data yet |
| Clickable KPI cards linking to reports | e.g. Pending Leave → leave requests list |
| Recent activity table | Not implemented |

### Icons & illustration

| | |
|---|---|
| **Current** | No icon set; hamburger is Unicode `☰` |
| **Nice to have** | Icon library (Lucide, Heroicons) for nav, status, export, empty states |

### Print styles

| | |
|---|---|
| **Applies to** | Report pages with tables |
| **Nice to have** | `@media print` — hide sidebar/header, full-width table, page breaks |

### Dark mode

| | |
|---|---|
| **Current** | Light mode only (sidebar is dark, content is light) |
| **Nice to have** | Optional `prefers-color-scheme` or toggle — low priority for internal HR tool |

---

## Site map

| Section | List URL | Add URL |
|---------|----------|---------|
| Dashboard | `/` | — |
| Employees | `/employees/` | `/employees/add/` |
| Punches | `/attendance/transactions/` | `/attendance/transactions/add/` |
| Daily attendance | `/attendance/daily/` | `/attendance/daily/add/` |
| Corrections | `/attendance/corrections/` | `/attendance/corrections/add/` |
| Rules | `/attendance/rules/` | `/attendance/rules/add/` |
| Leave types | `/leave/types/` | `/leave/types/add/` |
| Leave policies | `/leave/policies/` | `/leave/policies/add/` |
| Leave requests | `/leave/requests/` | `/leave/requests/add/` |
| Holidays | `/leave/holidays/` | `/leave/holidays/add/` |
| Timetables | `/schedule/timetables/` | `/schedule/timetables/add/` |
| Shifts | `/schedule/shifts/` | `/schedule/shifts/add/` |
| Assignments | `/schedule/assignments/` | `/schedule/assignments/add/` |
| Temporary | `/schedule/temporary/` | `/schedule/temporary/add/` |
| Reports hub | `/reports/` | — |
| Attendance summary | `/reports/attendance/` | — |
| Individual attendance | `/reports/individual/` | — |
| Department attendance | `/reports/department/` | — |
| Exceptions | `/reports/exceptions/` | — |
| Punch log | `/reports/punch-log/` | — |
| Overtime | `/reports/overtime/` | — |
| Leave reports | `/reports/leave/` | — |
| Profile | `/accounts/profile/` | — |
| Login | `/accounts/login/` | — |

List pages show a primary action button in the header (e.g. "Add employee" → `/employees/add/`).

---

## File reference

| What | Path |
|------|------|
| CSS | `static/css/app.css` |
| DataTables overrides (proposed) | `static/css/datatables-overrides.css` |
| JS | `static/js/app.js` |
| DataTables init (proposed) | `static/js/datatables-init.js` |
| Shell layout | `templates/layouts/app_shell.html` |
| Table partials | `templates/{app}/partials/*_table.html` |
| Form partials | `templates/{app}/partials/*_form.html` |
| Report filters | `templates/reports/partials/filter_form.html` |
| Pagination (legacy) | `templates/partials/pagination.html` |
| Form Python defs | `{app}/forms.py` |
| Page size constant | `common/pagination.py` (`DEFAULT_PAGE_SIZE = 25`) |

---

## DataTables integration

All **read-only data tables** (list pages + report pages) should use [DataTables](https://datatables.net/). The shift **formset table** on Add Shift is a form control — **do not** initialize DataTables on it.

### Scope

| Use DataTables | Do NOT use DataTables |
|----------------|----------------------|
| 13 CRUD list tables | `.formset-table` (shift cycle days) |
| 8 report result tables | Dashboard (KPI cards, not a table) |
| | Reports hub (link list) |

**Total: 21 tables**

### Current backend vs DataTables

Today the Django backend paginates at **25 rows per page** (`common/pagination.py`). List pages also use **HTMX live search** (`.search-input`) and **HTMX pagination** (`.pagination`). Report pages use **link pagination** (`pagination_mode: "link"`).

| Approach | Pros | Cons | When to use |
|----------|------|------|-------------|
| **Client-side DT** (Phase 1) | No backend changes; init on existing `<table>` HTML | Sort/search only affects **current page** (≤25 rows) | Quick win, small datasets |
| **Server-side DT** (Phase 2) | Full dataset sort, search, paginate | Requires new JSON API endpoints per table | Production, large datasets |
| **Hybrid** | Report filters stay Django GET; DT handles result table | Two filter UX layers if not careful | Reports with date filters |

**Recommendation:** Start client-side on each page load. Plan server-side endpoints for Employees, Punches, and high-volume reports.

### Markup changes (coordinate with backend)

Add a stable **`id`** and shared class to each data `<table>`:

```html
<table id="dt-employees" class="employee-table datatable">
```

| Class | Purpose |
|-------|---------|
| `.datatable` | JS hook — `document.querySelectorAll('table.datatable')` |
| `.employee-table` / `.data-table` | Keep for existing CSS |

**Remove or hide** when DataTables is active on a page:

- List page `.search-input` (DT has built-in search)
- `templates/partials/pagination.html` output (DT has built-in pagination)

Report pages: keep `.report-filters` (date range, department) — they reload the page via GET. DataTables then enhances the returned result table.

### Standard init (client-side)

```javascript
// static/js/datatables-init.js (proposed)
function initDataTable(selector, options) {
  const table = $(selector);
  if (!table.length || $.fn.DataTable.isDataTable(selector)) return;

  return table.DataTable({
    pageLength: 25,
    lengthMenu: [10, 25, 50, 100],
    order: options.order || [],
    columnDefs: options.columnDefs || [],
    responsive: true,
    language: {
      emptyTable: "No records found",
      search: "Search:",
      lengthMenu: "Show _MENU_ entries",
    },
    ...options,
  });
}
```

Per-table config (sort order, columnDefs) is in [Tables reference](#tables-reference) below.

### HTMX compatibility

List tables live inside HTMX swap targets (e.g. `#employee-list`). After HTMX replaces table HTML:

1. **Destroy** existing DataTable instance if present: `table.DataTable().destroy()`
2. **Re-init** on the new `<table>`

Listen for body events fired after successful add forms:

```javascript
document.body.addEventListener("employeeCreated", () => reinitTable("#dt-employees"));
// repeat for attendanceTransactionCreated, dailyAttendanceCreated, etc.
```

Or use HTMX `htmx:afterSwap` on the list container — check swap target contains `table.datatable`.

### Sorting HTML cells (badges, Yes/No, minutes)

DataTables sorts cell **text content** by default. For badges and formatted values, add **`data-order`** on `<td>` (backend template change):

```html
<!-- Badge: sort by status key, not label styling -->
<td data-order="pending"><span class="badge status-pending">Pending</span></td>

<!-- Minutes: sort numerically -->
<td data-order="120">120m</td>

<!-- Yes/No -->
<td data-order="1">Yes</td>
<td data-order="0">No</td>

<!-- Empty -->
<td data-order="">—</td>
```

Columns marked **Sort type: `html`** in the reference below need `data-order` for correct sort behavior.

### Recommended DataTables extensions

| Extension | Use for |
|-----------|---------|
| **Responsive** | Mobile — collapse columns |
| **FixedHeader** | Sticky `<thead>` on wide report tables (8–10 cols) |
| **Buttons** | Optional — duplicate report CSV/Excel/PDF export in DT toolbar |
| **DateTime** (sorting plug-in) | Timestamp columns if not using ISO `data-order` |

### DataTables DOM / CSS hooks to style

DataTables wraps the table and injects controls:

```
div.dataTables_wrapper
  div.dataTables_length      ← "Show N entries"
  div.dataTables_filter      ← global search input
  div.dataTables_info        ← "Showing 1 to 25 of …"
  div.dataTables_paginate    ← page buttons
table.dataTable              ← added class on init
  thead / tbody / tfoot
```

Style these to match app design tokens. Override default DataTables CSS via `static/css/datatables-overrides.css` (proposed).

### Empty state

Current templates show `.empty-state` **instead of** the table when count is zero. Two options:

1. **Keep Django empty state** — don't init DataTables when no rows
2. **Always render `<table>`** with empty tbody — use DataTables `emptyTable` language string

Pick one approach per page for consistency.

### Table ID registry

| Table ID | Page | Template partial |
|----------|------|------------------|
| `#dt-employees` | `/employees/` | `employee_table.html` |
| `#dt-punches` | `/attendance/transactions/` | `transaction_table.html` |
| `#dt-daily` | `/attendance/daily/` | `daily_table.html` |
| `#dt-corrections` | `/attendance/corrections/` | `correction_table.html` |
| `#dt-rules` | `/attendance/rules/` | `rule_table.html` |
| `#dt-leave-types` | `/leave/types/` | `leave_type_table.html` |
| `#dt-leave-policies` | `/leave/policies/` | `leave_policy_table.html` |
| `#dt-leave-requests` | `/leave/requests/` | `leave_request_table.html` |
| `#dt-holidays` | `/leave/holidays/` | `holiday_table.html` |
| `#dt-timetables` | `/schedule/timetables/` | `timetable_table.html` |
| `#dt-shifts` | `/schedule/shifts/` | `shift_table.html` |
| `#dt-assignments` | `/schedule/assignments/` | `assignment_table.html` |
| `#dt-temporary` | `/schedule/temporary/` | `temporary_table.html` |
| `#dt-report-attendance-summary` | `/reports/attendance/` | `attendance_summary_table.html` |
| `#dt-report-individual` | `/reports/individual/` | `individual_table.html` |
| `#dt-report-department` | `/reports/department/` | `department_table.html` |
| `#dt-report-exceptions` | `/reports/exceptions/` | `exceptions_table.html` |
| `#dt-report-punch-log` | `/reports/punch-log/` | `punch_log_table.html` |
| `#dt-report-overtime` | `/reports/overtime/` | `overtime_table.html` |
| `#dt-report-leave-balance` | `/reports/leave/` (balance) | `leave_balance_table.html` |
| `#dt-report-leave-requests` | `/reports/leave/` (util/pending) | `leave_requests_table.html` |

### Column definition legend

Used in every table below:

| Sort type | Meaning |
|-----------|---------|
| `string` | Plain text sort |
| `date` | ISO date (`YYYY-MM-DD`) — use `data-order` if displayed differently |
| `datetime` | ISO datetime — use `data-order` |
| `num` | Numeric — use `data-order` when cell shows suffix (`m`, ` days`) |
| `html` | Cell contains badges/markup — **requires `data-order`** on `<td>` |
| `—` | Not sortable — set `orderable: false` in `columnDefs` |

| Searchable | Meaning |
|------------|---------|
| Yes | Include in DataTables global search |
| No | Set `searchable: false` in `columnDefs` (e.g. some action columns) |

---

## Tables reference

Column headers match template `<th>` text. **DataTables ID** and per-column sort/search config are for frontend init. **Default sort** is the suggested `order` option on first load.

**Replaces (when DT active):** page `.search-input` + `.pagination` on list pages. Report filter forms stay.

---

### Employees list

| | |
|---|---|
| **Page URL** | `/employees/` |
| **DataTables ID** | `#dt-employees` |
| **Template** | `templates/employees/partials/employee_table.html` |
| **Table class** | `.employee-table.datatable` |
| **Default sort** | `[[1, 'asc']]` (Name) |
| **HTMX container** | `#employee-list` · refresh event: `employeeCreated` |
| **Replaces** | `#employee-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Code | Employee code or `—` | string | Yes | |
| 2 | Name | First + last name | string | Yes | Default sort column |
| 3 | Department | Department name or `—` | string | Yes | |
| 4 | Position | Position title or `—` | string | Yes | |
| 5 | Email | Email or `—` | string | Yes | |
| 6 | Username | Linked user username or `—` | string | Yes | |
| 7 | Status | Badge Active / Inactive | html | Yes | `data-order`: active=1, inactive=0 |

---

### Attendance punches list

| | |
|---|---|
| **Page URL** | `/attendance/transactions/` |
| **DataTables ID** | `#dt-punches` |
| **Template** | `templates/attendance/partials/transaction_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[1, 'desc']]` (Timestamp) |
| **HTMX container** | `#transaction-list` · refresh event: `attendanceTransactionCreated` |
| **Replaces** | `#transaction-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Employee | Full name | string | Yes | |
| 2 | Timestamp | Datetime | datetime | Yes | `data-order` ISO datetime |
| 3 | Direction | Check In / Check Out / Unknown | string | Yes | |
| 4 | Source | Biometric / Web / Mobile / Manual / Import | string | Yes | |
| 5 | External ID | External punch ID | string | Yes | |

---

### Daily attendance list

| | |
|---|---|
| **Page URL** | `/attendance/daily/` |
| **DataTables ID** | `#dt-daily` |
| **Template** | `templates/attendance/partials/daily_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc'], [1, 'asc']]` (Date, then Employee) |
| **HTMX container** | `#daily-list` · refresh event: `dailyAttendanceCreated` |
| **Replaces** | `#daily-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Date | Date | date | Yes | |
| 2 | Employee | Full name | string | Yes | |
| 3 | Status | Badge (Present, Absent, Late, …) | html | Yes | `data-order` = status key |
| 4 | Scheduled | Minutes + `m` | num | Yes | `data-order` = integer minutes |
| 5 | Worked | Minutes + `m` | num | Yes | `data-order` = integer minutes |
| 6 | Late | Minutes + `m` | num | Yes | `data-order` = integer minutes |
| 7 | OT | Overtime minutes + `m` | num | Yes | `data-order` = integer minutes |

---

### Attendance corrections list

| | |
|---|---|
| **Page URL** | `/attendance/corrections/` |
| **DataTables ID** | `#dt-corrections` |
| **Template** | `templates/attendance/partials/correction_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc']]` (Date) |
| **HTMX container** | `#correction-list` · refresh event: `attendanceCorrectionCreated` |
| **Replaces** | `#correction-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Date | Date | date | Yes | |
| 2 | Employee | Full name | string | Yes | |
| 3 | Check in | Datetime or `—` | datetime | Yes | `data-order` empty if `—` |
| 4 | Check out | Datetime or `—` | datetime | Yes | `data-order` empty if `—` |
| 5 | Status | Badge (Pending, Approved, …) | html | Yes | `data-order` = status key |
| 6 | Reason | Truncated to 8 words | string | Yes | Full text not in DOM — search limited |

---

### Attendance rules list

| | |
|---|---|
| **Page URL** | `/attendance/rules/` |
| **DataTables ID** | `#dt-rules` |
| **Template** | `templates/attendance/partials/rule_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'asc']]` (Name) |
| **HTMX container** | `#rule-list` · refresh event: `attendanceRuleCreated` |
| **Replaces** | `#rule-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Name | Rule name | string | Yes | |
| 2 | Late grace | Minutes + `m` | num | Yes | `data-order` = integer |
| 3 | Early grace | Minutes + `m` | num | Yes | `data-order` = integer |
| 4 | Multiple in/out | Yes / No | html | Yes | `data-order` 1/0 |
| 5 | Status | Badge Active / Inactive | html | Yes | `data-order` 1/0 |

---

### Leave types list

| | |
|---|---|
| **Page URL** | `/leave/types/` |
| **DataTables ID** | `#dt-leave-types` |
| **Template** | `templates/leave/partials/leave_type_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[1, 'asc']]` (Name) |
| **HTMX container** | `#leave-type-list` · refresh event: `leaveTypeCreated` |
| **Replaces** | `#leave-type-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Code | Leave type code | string | Yes | |
| 2 | Name | Leave type name | string | Yes | |
| 3 | Paid | Yes / No | html | Yes | `data-order` 1/0 |
| 4 | Approval | Required / No | html | Yes | `data-order` 1/0 |
| 5 | Half day | Yes / No | html | Yes | `data-order` 1/0 |
| 6 | Status | Badge Active / Inactive | html | Yes | `data-order` 1/0 |

---

### Leave policies list

| | |
|---|---|
| **Page URL** | `/leave/policies/` |
| **DataTables ID** | `#dt-leave-policies` |
| **Template** | `templates/leave/partials/leave_policy_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'asc']]` (Name) |
| **HTMX container** | `#leave-policy-list` · refresh event: `leavePolicyCreated` |
| **Replaces** | `#leave-policy-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Name | Policy name | string | Yes | |
| 2 | Leave type | Leave type name | string | Yes | |
| 3 | Entitlement | Days + ` days` | num | Yes | `data-order` = numeric days |
| 4 | Accrual | Accrual type display | string | Yes | |
| 5 | Carry forward | Yes / No | html | Yes | `data-order` 1/0 |
| 6 | Status | Badge Active / Inactive | html | Yes | `data-order` 1/0 |

---

### Leave requests list

| | |
|---|---|
| **Page URL** | `/leave/requests/` |
| **DataTables ID** | `#dt-leave-requests` |
| **Template** | `templates/leave/partials/leave_request_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[2, 'desc']]` (Start) |
| **HTMX container** | `#leave-request-list` · refresh event: `leaveRequestCreated` |
| **Replaces** | `#leave-request-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Employee | Full name | string | Yes | |
| 2 | Leave type | Leave type name | string | Yes | |
| 3 | Start | Start date | date | Yes | |
| 4 | End | End date | date | Yes | |
| 5 | Days | Number of days | num | Yes | |
| 6 | Status | Badge (Draft, Pending, …) | html | Yes | `data-order` = status key |

---

### Holidays list

| | |
|---|---|
| **Page URL** | `/leave/holidays/` |
| **DataTables ID** | `#dt-holidays` |
| **Template** | `templates/leave/partials/holiday_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[1, 'asc']]` (Date) |
| **HTMX container** | `#holiday-list` · refresh event: `holidayCreated` |
| **Replaces** | `#holiday-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Name | Holiday name | string | Yes | |
| 2 | Date | Start date | date | Yes | |
| 3 | End date | End date or `—` | date | Yes | |
| 4 | Type | Public / Company / Optional Holiday | string | Yes | |
| 5 | Status | Badge Active / Inactive | html | Yes | `data-order` 1/0 |

---

### Timetables list

| | |
|---|---|
| **Page URL** | `/schedule/timetables/` |
| **DataTables ID** | `#dt-timetables` |
| **Template** | `templates/schedule/partials/timetable_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[1, 'asc']]` (Name) |
| **HTMX container** | `#timetable-list` · refresh event: `timetableCreated` |
| **Replaces** | `#timetable-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Code | Timetable code | string | Yes | |
| 2 | Name | Timetable name | string | Yes | |
| 3 | Type | Normal / Flexible | string | Yes | |
| 4 | Work type | Work / Day Off / Overtime | string | Yes | |
| 5 | Check in | Time or `—` | string | Yes | `data-order` HH:MM if sorting times |
| 6 | Check out | Time or `—` | string | Yes | |
| 7 | Status | Badge Active / Inactive | html | Yes | `data-order` 1/0 |

---

### Shifts list

| | |
|---|---|
| **Page URL** | `/schedule/shifts/` |
| **DataTables ID** | `#dt-shifts` |
| **Template** | `templates/schedule/partials/shift_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[1, 'asc']]` (Name) |
| **HTMX container** | `#shift-list` · refresh event: `shiftCreated` |
| **Replaces** | `#shift-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Code | Shift code | string | Yes | |
| 2 | Name | Shift name | string | Yes | |
| 3 | Cycle | e.g. `7 weeks` | string | Yes | Composite text — sort as string |
| 4 | Days | Count of cycle days | num | Yes | |
| 5 | Auto shift | Yes / No | html | Yes | `data-order` 1/0 |
| 6 | Status | Badge Active / Inactive | html | Yes | `data-order` 1/0 |

---

### Schedule assignments list

| | |
|---|---|
| **Page URL** | `/schedule/assignments/` |
| **DataTables ID** | `#dt-assignments` |
| **Template** | `templates/schedule/partials/assignment_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[3, 'desc']]` (Start) |
| **HTMX container** | `#assignment-list` · refresh event: `assignmentCreated` |
| **Replaces** | `#assignment-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Type | Employee / Department / Group | string | Yes | |
| 2 | Target | Employee, department, or "Group" | string | Yes | |
| 3 | Shift | Shift name | string | Yes | |
| 4 | Start | Start date | date | Yes | |
| 5 | End | End date | date | Yes | |
| 6 | Overwrite | Yes / No | html | Yes | `data-order` 1/0 |

---

### Temporary schedules list

| | |
|---|---|
| **Page URL** | `/schedule/temporary/` |
| **DataTables ID** | `#dt-temporary` |
| **Template** | `templates/schedule/partials/temporary_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc']]` (Date) |
| **HTMX container** | `#temporary-list` · refresh event: `temporaryCreated` |
| **Replaces** | `#temporary-search`, `.pagination` |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Date | Date | date | Yes | |
| 2 | Employee | Full name | string | Yes | |
| 3 | Timetable | Timetable name | string | Yes | |
| 4 | Reason | Text or `—` | string | Yes | |
| 5 | Overrides | Yes / No | html | Yes | `data-order` 1/0 |

---

### Report: Attendance summary

| | |
|---|---|
| **Page URL** | `/reports/attendance/` |
| **DataTables ID** | `#dt-report-attendance-summary` |
| **Template** | `templates/reports/partials/attendance_summary_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'asc']]` (Employee) |
| **Pagination** | Replaces `.pagination` · keep `.report-filters` |
| **Extensions** | FixedHeader recommended (10 columns) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Employee | First + last name | string | Yes | |
| 2 | Department | Department name or `—` | string | Yes | |
| 3 | Total Days | Integer | num | Yes | |
| 4 | Present | Integer | num | Yes | |
| 5 | Absent | Integer | num | Yes | |
| 6 | Late | Integer | num | Yes | |
| 7 | Leave | Integer | num | Yes | |
| 8 | Worked | Minutes + `m` | num | Yes | `data-order` = integer |
| 9 | Late (min) | Minutes + `m` | num | Yes | `data-order` = integer |
| 10 | OT (min) | Minutes + `m` | num | Yes | `data-order` = integer |

---

### Report: Individual attendance

| | |
|---|---|
| **Page URL** | `/reports/individual/` |
| **DataTables ID** | `#dt-report-individual` |
| **Template** | `templates/reports/partials/individual_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc']]` (Date) |
| **Note** | Init DT only after employee selected and table rendered |
| **Extensions** | FixedHeader recommended (10 columns) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Date | Date | date | Yes | |
| 2 | Status | Badge | html | Yes | `data-order` = status key |
| 3 | Expected In | Time or `—` | string | Yes | |
| 4 | Expected Out | Time or `—` | string | Yes | |
| 5 | First In | Time or `—` | string | Yes | |
| 6 | Last Out | Time or `—` | string | Yes | |
| 7 | Worked | Minutes + `m` | num | Yes | `data-order` = integer |
| 8 | Late | Minutes + `m` | num | Yes | |
| 9 | Early Leave | Minutes + `m` | num | Yes | |
| 10 | OT | Minutes + `m` | num | Yes | |

---

### Report: Department attendance

| | |
|---|---|
| **Page URL** | `/reports/department/` |
| **DataTables ID** | `#dt-report-department` |
| **Template** | `templates/reports/partials/department_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'asc']]` (Department) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Department | Name or "Unassigned" | string | Yes | |
| 2 | Employees | Employee count | num | Yes | |
| 3 | Total Days | Integer | num | Yes | |
| 4 | Present | Integer | num | Yes | |
| 5 | Absent | Integer | num | Yes | |
| 6 | Late | Integer | num | Yes | |
| 7 | Late (min) | Minutes + `m` | num | Yes | |
| 8 | OT (min) | Minutes + `m` | num | Yes | |

---

### Report: Exceptions

| | |
|---|---|
| **Page URL** | `/reports/exceptions/` |
| **DataTables ID** | `#dt-report-exceptions` |
| **Template** | `templates/reports/partials/exceptions_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc']]` (Date) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Date | Date | date | Yes | |
| 2 | Employee | Full name | string | Yes | |
| 3 | Department | Department or `—` | string | Yes | |
| 4 | Status | Badge | html | Yes | `data-order` = status key |
| 5 | Check In | Yes / No | html | Yes | `data-order` 1/0 |
| 6 | Check Out | Yes / No | html | Yes | `data-order` 1/0 |
| 7 | Late (min) | Minutes + `m` | num | Yes | |
| 8 | Notes | Text or `—` | string | Yes | |

---

### Report: Punch log

| | |
|---|---|
| **Page URL** | `/reports/punch-log/` |
| **DataTables ID** | `#dt-report-punch-log` |
| **Template** | `templates/reports/partials/punch_log_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc']]` (Timestamp) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Timestamp | Datetime | datetime | Yes | `data-order` ISO datetime |
| 2 | Employee | Full name | string | Yes | |
| 3 | Department | Department or `—` | string | Yes | |
| 4 | Direction | Check In / Check Out / Unknown | string | Yes | |
| 5 | Source | Biometric / Web / Mobile / Manual / Import | string | Yes | |
| 6 | External ID | External punch ID | string | Yes | |

---

### Report: Overtime

| | |
|---|---|
| **Page URL** | `/reports/overtime/` |
| **DataTables ID** | `#dt-report-overtime` |
| **Template** | `templates/reports/partials/overtime_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'desc']]` (Date) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Date | Date | date | Yes | |
| 2 | Employee | Full name | string | Yes | |
| 3 | Department | Department or `—` | string | Yes | |
| 4 | Minutes | Minutes + `m` | num | Yes | |
| 5 | Status | Badge (Pending, Approved, …) | html | Yes | `data-order` = status key |
| 6 | Reason | Text or `—` | string | Yes | |

---

### Report: Leave balance

| | |
|---|---|
| **Page URL** | `/reports/leave/` (when report type = Balance) |
| **DataTables ID** | `#dt-report-leave-balance` |
| **Template** | `templates/reports/partials/leave_balance_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[0, 'asc'], [3, 'desc']]` (Employee, Year) |
| **Extensions** | FixedHeader recommended (10 columns) |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Employee | Full name | string | Yes | |
| 2 | Department | Department or `—` | string | Yes | |
| 3 | Leave Type | Leave type name | string | Yes | |
| 4 | Year | Integer year | num | Yes | |
| 5 | Entitled | Days (decimal) | num | Yes | |
| 6 | Carried | Carried forward days | num | Yes | |
| 7 | Adjustment | Adjustment days | num | Yes | |
| 8 | Used | Used days | num | Yes | |
| 9 | Pending | Pending days | num | Yes | |
| 10 | Available | Available days | num | Yes | |

---

### Report: Leave utilization / pending

| | |
|---|---|
| **Page URL** | `/reports/leave/` (when report type = Utilization or Pending) |
| **DataTables ID** | `#dt-report-leave-requests` |
| **Template** | `templates/reports/partials/leave_requests_table.html` |
| **Table class** | `.data-table.datatable` |
| **Default sort** | `[[3, 'desc']]` (Start) |
| **Note** | Same page toggles between balance vs this table — destroy/re-init when report type changes |

| # | Column header | Cell content | Sort type | Searchable | DT notes |
|---|---------------|--------------|-----------|------------|----------|
| 1 | Employee | Full name | string | Yes | |
| 2 | Department | Department or `—` | string | Yes | |
| 3 | Leave Type | Leave type name | string | Yes | |
| 4 | Start | Start date | date | Yes | |
| 5 | End | End date | date | Yes | |
| 6 | Days | Number of days | num | Yes | |
| 7 | Reason | Text or `—` | string | Yes | |

---

### Shift formset table — NOT DataTables

| | |
|---|---|
| **Page URL** | `/schedule/shifts/add/` |
| **Template** | `templates/schedule/partials/shift_form.html` |
| **Table class** | `.formset-table` |
| **DataTables** | **Excluded** — editable inline form rows, not read-only data |

| # | Column header | Cell content |
|---|---------------|--------------|
| 1 | Day # | Number input |
| 2 | Timetable | Select dropdown |
| 3 | Remove | Delete checkbox |

Up to 7 rows. Style as a form grid, not a DataTable.

---

*Update this doc when adding columns, fields, pages, or DataTables config.*
