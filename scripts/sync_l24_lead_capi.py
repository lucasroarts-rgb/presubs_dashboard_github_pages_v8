"""Server-side CAPI sync for L24 Lead events - reads real CRM rows, sends exactly
one Meta Lead event per row.

This replaces the client-side pixel firing for L24's "Lead" event (GTM tag
"FB - Lead", id 107, paused on 2026-09-25 after two client-side dedup attempts
- cookie race, referrer strip - both failed against real Twilead traffic).
Driving the count from the CRM instead of the browser removes the duplication
problem structurally: one CRM row = one CAPI call = one event_id, no race, no
dependency on referrer/cookie persistence.

Advanced Matching here is email + first_name only - launch17db.leads_l21 has
no phone column and no fbp/fbc (those are browser-only signals the CRM never
captured), so this trades device-level matching for guaranteed-accurate,
PII-complete identity matching. GA4/Google Ads Lead tags are unaffected by
this script - they stayed on the pageview-only fix (GTM v146) since they
weren't the ones this session's complaint was about.

Watermark-based: tracks the last synced CRM row id in a local JSON file so
reruns (e.g. from a scheduled task) never resend the same lead.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.meta_capi import send_lead  # noqa: E402

STATE_FILE = ROOT / "data" / "l24_capi_sync_state.json"


def load_env_file(path: Path) -> dict:
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_synced_id": 0}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> None:
    env = load_env_file(ROOT / ".env")
    state = load_state()
    last_id = state.get("last_synced_id", 0)

    conn = pymysql.connect(
        host=env["CRM_MYSQL_HOST"],
        user=env["CRM_MYSQL_USER"],
        password=env["CRM_MYSQL_PASSWORD"],
        database=env["CRM_MYSQL_DATABASE"],
        port=int(env.get("CRM_MYSQL_PORT", 3306)),
        charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email, first_name, data, url_first FROM launch17db.leads_l21 "
        "WHERE id > %s AND url_first LIKE %s ORDER BY id ASC",
        [last_id, "%l24-sign-ups%"],
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print(f"no new L24 leads since id {last_id}")
        return

    pixel_id = env["META_PIXEL_ID"]
    access_token = env["META_ACCESS_TOKEN"]

    sent = 0
    errors = 0
    max_id = last_id
    for row_id, email, first_name, lead_date, url_first in rows:
        event_id = f"l24-crm-lead-{row_id}"
        try:
            result = send_lead(
                pixel_id=pixel_id,
                access_token=access_token,
                event_id=event_id,
                event_time=int(time.time()),
                email=email,
                first_name=first_name,
                event_source_url=url_first,
            )
            events_received = result.get("events_received", 0)
            print(f"id={row_id} event_id={event_id} events_received={events_received}")
            sent += 1
        except Exception as exc:  # noqa: BLE001
            print(f"id={row_id} FAILED: {exc}")
            errors += 1
        max_id = row_id

    state["last_synced_id"] = max_id
    save_state(state)
    print(f"done: {sent} sent, {errors} failed, watermark now at {max_id}")


if __name__ == "__main__":
    main()
