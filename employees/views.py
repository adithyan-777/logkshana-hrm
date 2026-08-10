from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from employees.forms import EmployeeForm
from employees.selectors import employee_list
from employees.services import employee_create, employee_invite_link


def _render_form(
    request: HttpRequest, form: EmployeeForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/partials/employee_form.html",
        {"form": form, "success_message": success_message},
    )


def _render_invite(request: HttpRequest, employee, invite_link: str) -> HttpResponse:
    return render(
        request,
        "employees/partials/employee_invite.html",
        {"employee": employee, "invite_link": invite_link},
    )


@login_required
@require_http_methods(["GET"])
def employee_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    employees = employee_list(search=search)
    context = {"employees": employees, "search": search}

    if request.headers.get("HX-Request"):
        return render(request, "employees/partials/employee_table.html", context)

    return render(request, "employees/list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def employee_add(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = employee_create(**form.cleaned_data)
            invite_link = employee_invite_link(employee=employee, request=request)

            response = _render_invite(request, employee, invite_link)
            response["HX-Trigger"] = "employeeCreated"
            return response

        return _render_form(request, form)

    form = EmployeeForm()
    if request.headers.get("HX-Request"):
        return _render_form(request, form)

    return render(request, "employees/add.html", {"form": form})
