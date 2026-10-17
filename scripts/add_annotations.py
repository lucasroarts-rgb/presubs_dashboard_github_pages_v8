"""Add or replace timeline annotations in data/dashboard_config.json from a JSON file.

  python scripts/add_annotations.py path/to/annotations.json

The JSON is a list of {id, event_date, title, description, category}. Same id replaces the old entry.
A copy of the config is saved in backups/ before writing. The public site picks the annotations up on
the next generate_public_site run (the daily sync does it).
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "dashboard_config.json"
REQUIRED = ("id", "event_date", "title", "category")


def main() -> int:
    new = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for item in new:
        missing = [k for k in REQUIRED if not item.get(k)]
        if missing:
            raise SystemExit(f"annotation {item.get('id')} missing {missing}")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    backup = ROOT / "backups" / f"dashboard_config_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(CONFIG, backup)
    ids = {item["id"] for item in new}
    annotations = [a for a in config.get("annotations") or [] if a.get("id") not in ids] + new
    annotations.sort(key=lambda a: (str(a.get("event_date") or ""), str(a.get("title") or "")))
    config["annotations"] = annotations
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"backup {backup.name}; annotations now {len(annotations)} (+{len(ids)} added/replaced)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
