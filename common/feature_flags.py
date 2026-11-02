"""Per-tenant feature toggles.

A tenant turns features off by listing feature keys on
``Company.hidden_features`` (public-schema JSONField, e.g.
``["leave"]``). Nothing is hidden unless the key is listed, so defaults
stay "everything on".

This module is the single surface for all consumers:

- ``feature_hidden`` / ``features_hidden`` — reads (context processor,
  templates flow through ``nav_can``).
- ``feature_required`` — view decorator that 404s hidden URLs, so UI
  hiding is paired with server enforcement (a hidden link is not
  security; direct URL hits must fail too).
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse


class Feature:
    """Feature keys stored in ``Company.hidden_features``."""

    LEAVE = "leave"
    SCHEDULE = "schedule"


def features_hidden(tenant: Any) -> list[str]:
    """Hidden feature keys for the tenant; fail open (nothing hidden).

    A missing field, ``None``, a non-list value, or a non-tenant
    (public-schema stub) means no features are hidden.
    """
    hidden = getattr(tenant, "hidden_features", None)
    if not hidden or not isinstance(hidden, (list, tuple, set, frozenset)):
        return []
    return [key for key in hidden if isinstance(key, str)]


def feature_hidden(tenant: Any, key: str) -> bool:
    return key in features_hidden(tenant)


def feature_required(key: str) -> Callable[[Callable], Callable]:
    """View decorator: 404 the URL when the tenant hides ``key``.

    Applies to plain and HTMX requests alike (partials go through the
    same views). Permission checks stay in ``require_permission``; this
    only strips tenant-disabled features from the URL space.
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(
            request: HttpRequest, *args: Any, **kwargs: Any
        ) -> HttpResponse:
            if feature_hidden(getattr(request, "tenant", None), key):
                raise Http404
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
