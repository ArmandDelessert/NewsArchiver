"""Optional monitoring: a heartbeat to Healthchecks.io and error reports to Sentry.

Both are off until configured (HEARTBEAT_URL, SENTRY_DSN) and both are best effort: nothing here
ever raises, so a monitoring outage can never take the application down.

Privacy: this sends data to third parties, which the rest of the project otherwise avoids. Sentry
is initialised without personal data, request bodies or local variables. Log lines and exception
messages can still end up in a report, so keep message contents out of them.

This file has no dependency on the rest of the project (stdlib only, `sentry_sdk` is imported
lazily) and is kept identical in the other repositories that use it.
"""
from __future__ import annotations

import logging
import urllib.error
import urllib.request
from typing import Literal

logger = logging.getLogger(__name__)

PING_TIMEOUT_SECONDS = 5.0
# Healthchecks.io keeps the first 100 kB of a ping body; a short note is all that is useful.
MAX_MESSAGE_CHARS = 1000

Status = Literal["ok", "fail", "start"]
_SUFFIX = {"ok": "", "fail": "/fail", "start": "/start"}


def ping(url: str, status: Status = "ok", message: str = "") -> bool:
    """Tells Healthchecks.io the job is alive ("ok"), failed ("fail") or beginning ("start").

    `url` is the check's ping URL (https://hc-ping.com/<uuid>); blank = disabled. The message is
    attached to the ping and shown on the check's page. Returns whether the ping was delivered.
    """
    if not url:
        return False
    target = url.rstrip("/") + _SUFFIX[status]
    body = message[:MAX_MESSAGE_CHARS].encode("utf-8", errors="replace") if message else None
    request = urllib.request.Request(target, data=body, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(request, timeout=PING_TIMEOUT_SECONDS) as response:  # noqa: S310
            return 200 <= response.status < 300
    except (OSError, ValueError, urllib.error.URLError) as exc:
        # The URL carries the check's secret: log the error class only, never the target.
        logger.warning("heartbeat not delivered (%s)", type(exc).__name__)
        return False


def init_sentry(dsn: str, *, release: str = "", environment: str = "", service: str = "") -> bool:
    """Starts error reporting; returns whether it is on. Blank DSN or missing package = off."""
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed: pip install sentry-sdk")
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            release=release or None,
            environment=environment or None,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            # Errors only: no performance traces, no profiling.
            traces_sample_rate=0.0,
        )
        if service:
            sentry_sdk.set_tag("service", service)
    except Exception:  # noqa: BLE001 - a bad DSN must not stop the application
        logger.warning("Sentry could not be initialised (bad SENTRY_DSN?)")
        return False
    return True


def capture_exception(exc: BaseException) -> None:
    """Reports an exception that was caught and handled (unhandled ones are reported by Sentry itself)."""
    try:
        import sentry_sdk
    except ImportError:
        return
    try:
        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        pass


def flush(timeout: float = 2.0) -> None:
    """Sends the pending reports: a short-lived process must call it before exiting."""
    try:
        import sentry_sdk
    except ImportError:
        return
    try:
        sentry_sdk.flush(timeout=timeout)
    except Exception:  # noqa: BLE001
        pass
