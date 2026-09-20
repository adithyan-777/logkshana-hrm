"""Round name-avatar helpers: deterministic initials + color variant.

Usage:
    {% load avatar %}
    {% avatar employee %}
    {% avatar employee size="sm" %}
    {% avatar request.user size="md" %}
    {% avatar "Adithyan Krishna" size="lg" %}
    {% avatar first_name="Jane" last_name="Doe" size="md" %}
"""

import hashlib

from django import template

register = template.Library()

SIZES = {"xs", "sm", "md", "lg", "xl"}
VARIANT_COUNT = 8


def _variant_for(seed: str) -> int:
    digest = hashlib.md5((seed or "?").lower().encode("utf-8")).hexdigest()
    return int(digest[:2], 16) % VARIANT_COUNT


def _initials_from_words(words: list[str], fallback: str = "") -> str:
    cleaned = [w.strip() for w in words if w and w.strip()]
    if len(cleaned) >= 2:
        return f"{cleaned[0][0]}{cleaned[-1][0]}".upper()
    if len(cleaned) == 1:
        word = "".join(ch for ch in cleaned[0] if ch.isalnum())
        if not word:
            word = (fallback or "?").strip()
        return (word[:2] if len(word) > 1 else word[:1] or "?").upper()
    alnum = "".join(ch for ch in (fallback or "") if ch.isalnum())
    return (alnum[:2] or "?").upper()


@register.inclusion_tag("partials/emp_avatar.html")
def avatar(person=None, size="md", first_name="", last_name="", label=""):
    size = size if size in SIZES else "md"

    # Explicit first/last override wins.
    if first_name or last_name:
        initials = _initials_from_words([first_name, last_name])
        seed = f"{first_name} {last_name}".strip()
        return {
            "initials": initials,
            "variant": _variant_for(seed),
            "size": size,
            "label": label or seed,
        }

    # Employee-like (has initials/avatar_variant properties).
    if person is not None and hasattr(person, "initials"):
        try:
            initials = person.initials or "?"
        except Exception:  # noqa: BLE001 -- never break a page on avatar
            initials = "?"
        try:
            variant = int(person.avatar_variant) % VARIANT_COUNT
        except Exception:  # noqa: BLE001
            variant = _variant_for(str(person))
        display = label or getattr(person, "full_name", None) or str(person)
        return {"initials": initials, "variant": variant, "size": size, "label": display}

    # User-like (has get_username).
    if person is not None and hasattr(person, "get_username"):
        try:
            full = person.get_full_name()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            full = ""
        username = ""
        try:
            username = person.get_username()
        except Exception:  # noqa: BLE001
            username = ""
        email = getattr(person, "email", "") or ""
        display = label or full or username or email
        parts = (full or "").split()
        if parts:
            initials = _initials_from_words(parts, fallback=username or email)
        else:
            # username/email slicing keeps the old 2-char look for logins.
            alnum = "".join(ch for ch in (username or email) if ch.isalnum())
            initials = (alnum[:2] or "?").upper()
        return {
            "initials": initials,
            "variant": _variant_for(username or email or display),
            "size": size,
            "label": display,
        }

    # Plain string / anything else.
    text = label or (str(person) if person not in (None, "") else "")
    initials = _initials_from_words(text.split(), fallback=text) if text else "?"
    return {
        "initials": initials,
        "variant": _variant_for(text),
        "size": size,
        "label": text,
    }
