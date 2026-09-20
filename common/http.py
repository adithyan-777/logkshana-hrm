import json

from django.http import HttpRequest, HttpResponse


def is_htmx_partial(request: HttpRequest) -> bool:
    """Return True for HTMX fragment requests, not boosted SPA navigations.

    History restores re-fetch the pushed URL with HX-History-Restore-Request;
    they must get a full page, otherwise back/forward renders a bare fragment.
    """
    if not request.headers.get("HX-Request"):
        return False
    if request.headers.get("HX-History-Restore-Request"):
        return False
    return not request.headers.get("HX-Boosted")


def set_hx_trigger(
    response: HttpResponse,
    *,
    event: str,
    toast: str | None = None,
    close_modal: bool = True,
) -> HttpResponse:
    """Attach a JSON HX-Trigger for list refresh, optional toast, and drawer close."""
    payload: dict[str, object] = {event: True}
    if close_modal:
        payload["closeModal"] = True
    if toast:
        payload["showToast"] = {"message": toast, "type": "success"}
    response["HX-Trigger"] = json.dumps(payload)
    return response
