"""Meta Conversions API (CAPI) - server-side CompleteRegistration sender.

The browser pixel on the thank-you page (see scripts/meta_capi_snippet.js)
misses conversions whenever the browser blocks connect.facebook.net (ad
blockers, Safari ITP, Brave, uBlock...) - a structural gap, not a bug, that
no client-side fix can close.

This module sends the same "CompleteRegistration" event from the server
instead, at the moment a lead/booking is actually confirmed - wherever that
happens (the webhook that writes to the CRM `leads`/`meetings` table).
That system must call `send_complete_registration()` below, using the SAME
`event_id` the browser page used, so Meta deduplicates the two into a
single conversion instead of double-counting.

This file has no dependency on the rest of this project besides `requests`
(and optionally `.env` if run from here) - it can be copied into whatever
backend owns lead/booking confirmation if that is a different codebase.

Usage:
    from scripts.meta_capi import send_complete_registration

    send_complete_registration(
        pixel_id=PIXEL_ID,
        access_token=ACCESS_TOKEN,
        event_id=event_id,          # same id the browser pixel sent
        email=lead_email,           # raw email - this function hashes it
        phone=lead_phone,           # optional, raw phone
        event_source_url=confirmation_page_url,
    )
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import requests

CAPI_URL = "https://graph.facebook.com/v21.0/{pixel_id}/events"


def _hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def send_complete_registration(
    *,
    pixel_id: str,
    access_token: str,
    event_id: str,
    email: str | None = None,
    phone: str | None = None,
    client_ip_address: str | None = None,
    client_user_agent: str | None = None,
    fbc: str | None = None,
    fbp: str | None = None,
    event_source_url: str | None = None,
    content_name: str = "RDV Programme Complet",
    content_category: str = "Rendez-vous confirme",
    test_event_code: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """POST a server-side CompleteRegistration event to Meta CAPI.

    `event_id` must match the id the browser pixel used for the same
    conversion (see scripts/meta_capi_snippet.js) so Meta dedupes browser
    and server into one event instead of counting it twice.

    `email`/`phone` are raw values - Meta requires them SHA-256 hashed,
    which happens here. Never log or store the raw values beyond this call.

    Pass `test_event_code` (from Events Manager > Test Events) while
    validating the integration - test events do not affect real reporting.
    """
    user_data: dict[str, Any] = {}
    if email:
        user_data["em"] = [_hash(email)]
    if phone:
        user_data["ph"] = [_hash(phone)]
    if client_ip_address:
        user_data["client_ip_address"] = client_ip_address
    if client_user_agent:
        user_data["client_user_agent"] = client_user_agent
    if fbc:
        user_data["fbc"] = fbc
    if fbp:
        user_data["fbp"] = fbp

    if not user_data:
        raise ValueError(
            "At least one of email, phone, fbc or fbp is required for Meta "
            "to be able to match this event to a person."
        )

    event: dict[str, Any] = {
        "event_name": "CompleteRegistration",
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {
            "content_name": content_name,
            "content_category": content_category,
        },
    }
    if event_source_url:
        event["event_source_url"] = event_source_url

    payload: dict[str, Any] = {"data": [event]}
    if test_event_code:
        payload["test_event_code"] = test_event_code

    response = requests.post(
        CAPI_URL.format(pixel_id=pixel_id),
        params={"access_token": access_token},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
