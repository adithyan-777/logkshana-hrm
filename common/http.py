from django.http import HttpRequest


def is_htmx_partial(request: HttpRequest) -> bool:
    """Return True for HTMX fragment requests, not boosted SPA navigations."""
    if not request.headers.get("HX-Request"):
        return False
    return not request.headers.get("HX-Boosted")
