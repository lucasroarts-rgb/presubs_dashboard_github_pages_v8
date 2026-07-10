from __future__ import annotations

import importlib.util
import sys

MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pandas": "pandas",
    "openpyxl": "openpyxl",
    "python-multipart": "multipart",
}

missing = [
    package
    for package, module in MODULES.items()
    if importlib.util.find_spec(module) is None
]

if missing:
    print("Missing packages: " + ", ".join(missing))
    sys.exit(1)

print("Dependencies OK")
