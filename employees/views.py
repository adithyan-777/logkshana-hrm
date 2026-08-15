from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from common.http import is_htmx_partial
from common.pagination import list_pagination_context
from employees.forms import EmployeeForm
from employees.selectors import employee_list
from employees.services import employee_create, employee_invite_link


def _render_form(
    request: HttpRequest, form: EmployeeForm, *, success_message: str = ""
) -> HttpResponse:
    return render(
        request,
        "employees/add.html#employee_form",
        {"form": form, "success_message": success_message},
    )


def _render_invite(request: HttpRequest, employee, invite_link: str) -> HttpResponse:
    return render(
        request,
        "employees/add.html#employee_invite",
        {"employee": employee, "invite_link": invite_link},
    )


@login_required
@require_http_methods(["GET"])
def employee_list_view(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    context = list_pagination_context(
        request,
        employee_list(search=search),
        search=search,
        base_url=reverse("employee_list"),
        hx_target="#employee-list",
    )

    if is_htmx_partial(request):
        return render(request, "employees/list.html#employee_table", context)

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
    if is_htmx_partial(request):
        return _render_form(request, form)

    return render(request, "employees/add.html", {"form": form})
