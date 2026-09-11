from django.http import HttpRequest


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
