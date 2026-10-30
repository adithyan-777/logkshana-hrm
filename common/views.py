"""App-agnostic HTMX fragment endpoints for reusable UI partials."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.urls import reverse

from common.http import is_htmx_partial
from employees.models import Employee
from employees.permission_catalog import PermissionCodename
from employees.selectors import user_has_permission


def _employee_options(q: str) -> list[dict]:
    """First 20 active employees, filtered by name/code/email when q is given."""
    queryset = Employee.objects.filter(is_active=True).order_by(
        "first_name", "last_name"
    )
    if q:
        queryset = queryset.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(emp_code__icontains=q)
            | Q(email__icontains=q)
        )
    return [
        {"value": str(emp.pk), "label": f"{emp.full_name} ({emp.emp_code})"}
        for emp in queryset[:20]
    ]


# Registry for common.select_options_view. One entry per option source; the
# widget only ever renders the fragment, forms still receive real values.
SOURCES: dict[str, dict] = {
    "employees": {
        "permissions": (
            PermissionCodename.REPORTS_VIEW,
            PermissionCodename.EMPLOYEES_VIEW,
            PermissionCodename.ATTENDANCE_VIEW,
            PermissionCodename.ATTENDANCE_ADD,
            PermissionCodename.SCHEDULE_VIEW,
            PermissionCodename.SCHEDULE_ADD,
        ),
        "options": _employee_options,
    },
}


def redirect_stale_fragment_visit(
    request: HttpRequest,
    *,
    fallback_url_name: str,
    follow_referer: bool = False,
    fragment_path: str = "",
) -> HttpResponseRedirect:
    """Redirect a non-HTMX browser visit of an HTMX-only fragment endpoint.

    Bare fragment visits come from Back buttons on stale history entries,
    reloads of previously pushed URLs, or pasted links — never real user
    intent, so the redirect must be deterministic:
    - anonymous users go to login;
    - with ``follow_referer=True``, authenticated users go back to the page
      they came from — except when the Referer is the fragment URL itself
      (a reload of a previously pushed URL carries it as its own Referer;
      redirecting to it would loop);
    - everything else goes to ``fallback_url_name``.

    Default is deterministic-only (``follow_referer=False``): a reload
    referer may be the tab's historical committed document, i.e. an
    arbitrary old page the user never asked for (observed: the exceptions
    report), so aux option endpoints should not trust it.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("account_login"))
    if follow_referer:
        referer = request.META.get("HTTP_REFERER") or ""
        if referer and not (fragment_path and fragment_path in referer):
            return HttpResponseRedirect(referer)
    return HttpResponseRedirect(reverse(fallback_url_name))


def select_options_view(request: HttpRequest) -> HttpResponse:
    """HTMX fragment: options for the reusable select partial.

    Query params:
      ?source=<registry key>   ,?q=<free text> (empty string → initial page;
                               single-char queries return "" — treat as noise),
      ?target=<widget uid>     (ignorable), ?selected=<initial value> to mark.

    Non-HTMX browser visits (Back button on stale history entries, refresh of
    a pushed URL, pasted links) are redirected back out: this view has no
    full-page form, so a bare fragment would be broken to look at. They
    always land on the Reports landing page — the referer is *not* trusted
    here, because on reloads it is the tab's historical committed document
    and can be an arbitrary old page (observed: the exceptions report).
    Anonymous visits bounce to the login page.
    Rendered for ``partials/select_options.html``.
    """
    if not is_htmx_partial(request):
        return redirect_stale_fragment_visit(
            request,
            fallback_url_name="report_hub",
        )
    source = request.GET.get("source", "")
    entry = SOURCES.get(source)
    if entry is None:
        raise Http404(f"Unknown select source: {source!r}")
    allowed = any(
        user_has_permission(user=request.user, codename=code)
        for code in entry["permissions"]
    )
    if not allowed:
        raise PermissionDenied
    q = request.GET.get("q", "").strip()
    if len(q) == 1:
        return HttpResponse("")
    return render(
        request,
        "partials/select_options.html",
        {
            "options": entry["options"](q),
            "query": q,
            "selected": request.GET.get("selected", ""),
        },
    )
