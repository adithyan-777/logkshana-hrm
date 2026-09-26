import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ValidationError


def gateway_auth_headers() -> dict:
    """Auth headers pattika sends when calling the device gateway.

    Canonical scheme is ``Authorization: Bearer <GATEWAY_SECRET_KEY>``.
    ``X-Gateway-Token`` is sent as well for gateways that prefer a custom
    header. Empty dict when no secret is configured (local dev).
    """
    secret = getattr(settings, "GATEWAY_SECRET_KEY", "") or ""
    if not secret:
        return {}
    return {"Authorization": f"Bearer {secret}", "X-Gateway-Token": secret}


#: Substrings marking a gateway failure as transient (safe to retry).
#: Permanent failures (unknown device, 4xx, missing emp_code) carry no
#: marker and must fail fast so bad tasks don't loop forever.
TRANSIENT_GATEWAY_MARKERS = (
    "502",
    "503",
    "504",
    "500",
    "Gateway unreachable",
    "unreachable",
    "timeout",
    "timed out",
)


def is_transient_gateway_error(
    exc: BaseException, *, field_keys=("device_gateway",)
) -> bool:
    """Whether a device-gateway failure is transient (worth retrying).

    Raw network errors (HTTPError 5xx, URLError, TimeoutError, OSError)
    are always transient. ValidationErrors wrapping gateway responses are
    transient only when they carry one of ``field_keys`` *and* a transient
    marker — e.g. a wrapped 502. Everything else (unknown device, 4xx,
    missing emp_code) is permanent and must not be retried.
    """
    if isinstance(exc, (HTTPError, URLError, TimeoutError, OSError)):
        return True
    if isinstance(exc, ValidationError):
        msg_dict = getattr(exc, "message_dict", {}) or {}
        if not any(key in msg_dict for key in field_keys):
            return False
        parts: list[str] = []
        for key in field_keys:
            msgs = msg_dict.get(key, [])
            parts.extend(msgs if isinstance(msgs, list) else [msgs])
        check_str = " ".join(str(m) for m in parts) or str(exc)
        return any(marker in check_str for marker in TRANSIENT_GATEWAY_MARKERS)
    return False


def gateway_request_is_authorized(request) -> bool:
    """Check a request arriving from the device gateway.

    Accepts (in order):
    - ``Authorization: Bearer <GATEWAY_SECRET_KEY>`` (canonical)
    - ``X-Gateway-Token: <GATEWAY_SECRET_KEY>``
    - legacy ``?secret_key=<GATEWAY_SECRET_KEY>`` query param

    Returns True when no ``GATEWAY_SECRET_KEY`` is configured so local dev
    without a secret keeps working.
    """
    secret = getattr(settings, "GATEWAY_SECRET_KEY", "") or ""
    if not secret:
        return True
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth == f"Bearer {secret}":
        return True
    if request.META.get("HTTP_X_GATEWAY_TOKEN") == secret:
        return True
    # Legacy fallback for gateways that can only append a query param.
    if request.GET.get("secret_key") == secret:
        return True
    return False


def device_gateway_attendance_fetch(
    *,
    serial_number: str,
    after_id: int | None = None,
) -> list[dict]:
    base_url = settings.DEVICE_GATEWAY_BASE_URL
    if not base_url:
        raise ValidationError(
            {"device_gateway": "DEVICE_GATEWAY_BASE_URL is not configured."}
        )

    params = {"serial_number": serial_number}
    if after_id is not None:
        params["after_id"] = after_id

    url = f"{base_url.rstrip('/')}/api/attendance?{urlencode(params)}"
    headers = {"Accept": "application/json", **gateway_auth_headers()}
    request = Request(url, method="GET", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            payload = json.loads(raw)
    except HTTPError as exc:
        # 5xx are transient (e.g. 502 Bad Gateway) — re-raise as HTTPError
        # so the task layer can retry. 4xx are permanent validation errors.
        if 500 <= exc.code < 600:
            # Include gateway URL in the HTTPError message for debugging
            # while preserving original code/reason for retry logic.
            try:
                body = (
                    exc.read().decode(errors="ignore")[:500]
                    if hasattr(exc, "read")
                    else ""
                )
            except Exception:
                body = ""
            detail = f" body: {body}" if body else ""
            # Re-raise with enriched message but same code so caller sees URL + code
            # Keep original exception chain for debugging
            raise HTTPError(
                exc.url,
                exc.code,
                f"{exc.msg} for {url}.{detail} (base: {base_url})",
                exc.headers,
                exc.fp,
            ) from exc
        # 4xx — permanent, wrap as ValidationError (no retry)
        try:
            body = (
                exc.read().decode(errors="ignore")[:500] if hasattr(exc, "read") else ""
            )
        except Exception:
            body = ""
        detail = f" body: {body}" if body else ""
        raise ValidationError(
            {
                "device_gateway": f"Gateway returned HTTP {exc.code}.{detail} for {url} (base: {base_url})"
            }
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        # Transient network errors — re-raise directly so the task layer
        # can retry (q2 bounded retry on transient failures).
        # Add context about the base URL for debugging
        if isinstance(exc, URLError):
            raise URLError(
                f"Gateway unreachable at {base_url} ({url}): {exc.reason}"
            ) from exc
        raise

    if not isinstance(payload, list):
        raise ValidationError(
            {"device_gateway": "Gateway returned an invalid payload."}
        )

    return payload
