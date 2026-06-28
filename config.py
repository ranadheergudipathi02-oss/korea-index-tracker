"""Central configuration for the Static Korea Index Tracker."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")          # JSON storage root (served by Pages)
CURRENT = os.path.join(DATA, "current")    # current/<id>.json, overwritten each run
CHANGES = os.path.join(DATA, "changes.jsonl")
META = os.path.join(DATA, "meta.json")
INDICES = os.path.join(DATA, "indices.json")  # registry: id -> {name,category,...}

# --- Throttling / retries (survival mechanics; we hit Korea from an Indian IP) ---
THROTTLE_SEC = 0.30        # base sleep between requests
RETRY_MAX = 4              # attempts per request
RETRY_BACKOFF = 1.8        # exponential backoff multiplier
REQUEST_TIMEOUT = 20

# --- Correctness guard ---
# Skip diff+write for an index whose new fetch is empty OR drops more than this
# fraction vs the last snapshot (primary corruption guard).
GUARD_DROP_FRACTION = 0.40   # >40% shrink => treat as suspect, mark failed, don't write
GUARD_MIN_MEMBERS = 1        # empty fetch always fails the guard

# --- Allow-list: which categories to track (user picked ALL four). ---
# Static benchmark + full-market indices (fixed identity).
STATIC_INDICES = [
    {"id": "kospi-200", "name": "KOSPI 200", "category": "broad",
     "method": "entry", "type": "KPI200"},
    {"id": "kospi-100", "name": "KOSPI 100", "category": "broad",
     "method": "entry", "type": "KPI100"},
    {"id": "kospi", "name": "KOSPI (Composite, all listed)", "category": "broad",
     "method": "market", "sosok": 0},
    {"id": "kosdaq", "name": "KOSDAQ (Composite, all listed)", "category": "broad",
     "method": "market", "sosok": 1},
]

# Dynamic group categories: (naver_group_type, our_category, id_prefix, enabled)
GROUP_CATEGORIES = [
    ("upjong", "sector", "sector", True),   # 79 industry/sector groups
    ("group", "group", "group", True),      # 61 conglomerate (그룹사) groups
    ("theme", "theme", "theme", True),      # 265 Naver theme groups
]

# Known-unavailable official indices (documented for the frontend "gaps" note).
UNAVAILABLE = [
    "KOSDAQ 150", "KOSPI 50", "KRX 100", "KRX 300",
    "KRX sector / ESG / dividend indices",
]
