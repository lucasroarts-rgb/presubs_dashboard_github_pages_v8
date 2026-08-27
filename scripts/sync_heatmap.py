"""Sync click/scroll heatmap data from Firestore.

Firestore is used as a transient inbox, not permanent storage: the site's
tracker (firebase/heatmap-tracker.html) writes one document per pageview
to the "pageviews" collection, this script reads every document, folds it
into local aggregates (a coarse click-density grid and a scroll-depth
funnel, per path+device), then DELETES the documents it just processed.
This keeps the Firestore collection small (avoids hitting free-tier
read/write quotas over time) and means the local SQLite aggregates ARE
the permanent record, not Firestore itself.

Requires a Firebase service account key at
data/firebase_service_account.json (gitignored - this is a private
credential, never commit it).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402

SERVICE_ACCOUNT_PATH = ROOT / "data" / "firebase_service_account.json"
GRID_COLS = dashboard_app.HEATMAP_GRID_COLS
GRID_ROWS = dashboard_app.HEATMAP_GRID_ROWS
BATCH_DELETE_SIZE = 400  # Firestore batch writes cap at 500 operations


class HeatmapSyncError(RuntimeError):
    pass


def _client():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not SERVICE_ACCOUNT_PATH.exists():
        raise HeatmapSyncError(f"Missing Firebase service account key at {SERVICE_ACCOUNT_PATH}")

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
        firebase_admin.initialize_app(cred)
    return firestore.client()


def fetch_pageviews(client) -> list[dict]:
    docs = list(client.collection("pageviews").stream())
    rows = []
    for doc in docs:
        data = doc.to_dict() or {}
        rows.append({"id": doc.id, **data})
    return rows


def delete_pageviews(client, doc_ids: list[str]) -> None:
    for i in range(0, len(doc_ids), BATCH_DELETE_SIZE):
        batch = client.batch()
        for doc_id in doc_ids[i:i + BATCH_DELETE_SIZE]:
            batch.delete(client.collection("pageviews").document(doc_id))
        batch.commit()


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def aggregate(rows: list[dict]) -> tuple[dict, dict, dict]:
    """Returns (page_totals, click_grid, scroll_buckets), each keyed by
    (path, device)."""
    page_totals: dict[tuple[str, str], dict[str, int]] = {}
    click_grid: dict[tuple[str, str, int, int], int] = {}
    scroll_buckets: dict[tuple[str, str, int], int] = {}

    for row in rows:
        path = row.get("path")
        device = row.get("device")
        if not path or device not in ("mobile", "tablet", "desktop"):
            continue
        key = (path, device)

        totals = page_totals.setdefault(key, {"pageview_count": 0, "click_count": 0})
        totals["pageview_count"] += 1

        for click in row.get("clicks") or []:
            x_pct = clip(float(click.get("x_pct") or 0), 0, 99.999)
            y_pct = clip(float(click.get("y_pct") or 0), 0, 99.999)
            col = int(x_pct / 100 * GRID_COLS)
            grid_row = int(y_pct / 100 * GRID_ROWS)
            click_grid[(path, device, col, grid_row)] = click_grid.get((path, device, col, grid_row), 0) + 1
            totals["click_count"] += 1

        max_scroll = clip(float(row.get("max_scroll_pct") or 0), 0, 100)
        # A session that reached max_scroll X counts toward every bucket <= X
        # (classic "% of visitors who scrolled at least this far" funnel).
        for bucket in range(0, int(max_scroll) + 1, 10):
            scroll_buckets[(path, device, bucket)] = scroll_buckets.get((path, device, bucket), 0) + 1

    return page_totals, click_grid, scroll_buckets


def store(page_totals: dict, click_grid: dict, scroll_buckets: dict) -> None:
    with dashboard_app.db() as con:
        for (path, device), totals in page_totals.items():
            con.execute(
                """
                INSERT INTO heatmap_pages (path, device, pageview_count, click_count, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path, device) DO UPDATE SET
                    pageview_count = heatmap_pages.pageview_count + excluded.pageview_count,
                    click_count = heatmap_pages.click_count + excluded.click_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (path, device, totals["pageview_count"], totals["click_count"]),
            )
        for (path, device, col, row), count in click_grid.items():
            con.execute(
                """
                INSERT INTO heatmap_click_grid (path, device, grid_col, grid_row, click_count, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path, device, grid_col, grid_row) DO UPDATE SET
                    click_count = heatmap_click_grid.click_count + excluded.click_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (path, device, col, row, count),
            )
        for (path, device, bucket), count in scroll_buckets.items():
            con.execute(
                """
                INSERT INTO heatmap_scroll_depth (path, device, depth_bucket, session_count, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(path, device, depth_bucket) DO UPDATE SET
                    session_count = heatmap_scroll_depth.session_count + excluded.session_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (path, device, bucket, count),
            )


def main() -> int:
    dashboard_app.init_db()
    client = _client()

    rows = fetch_pageviews(client)
    if not rows:
        print("Heatmap sync: no new pageviews in Firestore - nothing to do.")
        return 0

    page_totals, click_grid, scroll_buckets = aggregate(rows)
    store(page_totals, click_grid, scroll_buckets)
    delete_pageviews(client, [row["id"] for row in rows])

    print(
        f"Heatmap sync complete: {len(rows)} pageviews processed, "
        f"{len(page_totals)} path+device combos, {sum(t['click_count'] for t in page_totals.values())} clicks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
