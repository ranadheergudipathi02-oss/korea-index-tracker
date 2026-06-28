# Static Korea Index Tracker

An always-on reference site cataloguing **KOSPI + KOSDAQ** index constituents with
auto-tracked **add/remove history**. Same architecture as the NSE/BSE (India) and
China static index trackers — only the data-sourcing layer differs.

- **Fetcher**: runs locally on a Windows PC, daily via Task Scheduler.
- **Storage**: this Git repo, pure JSON flat files, append-only. No database.
- **Serving**: GitHub Pages — 100 % static HTML/JS reading the JSON, 24/7,
  independent of the PC. Data updates only when the PC runs (KRX reconstitutes
  ~2×/yr, so a PC-off day rarely costs anything). **Change date = detection date.**

## Data source

Naver Finance (`finance.naver.com`), anonymous — no account, no token.
KRX's own portal (`data.krx.co.kr`) now requires a logged-in Korean account, so
it is **not** used (see `docs notes` / project memory). Trade-offs of Naver:

- ✅ KOSPI 200, KOSPI 100, full KOSPI, full KOSDAQ, 79 sectors, 61 business
  groups, 265 themes.
- ❌ No KOSDAQ 150 / KOSPI 50 / KRX 100 / KRX 300 / official ESG/dividend indices
  (no anonymous endpoint). ❌ No ISIN (we key on the stable 6-digit code).

## Layout

```
config.py          allow-list, throttle, guard thresholds
naver_source.py    Naver fetchers (EUC-KR, throttle+retry+backoff, pagination)
diff_engine.py     snapshot guard, first-run baseline, append-only changes.jsonl
fetcher.py         build registry -> fetch all -> reconcile -> meta.json
build_site.py      JSON -> data/summary.json (directory, recent feed, stock->index)
run_daily.py       fetch -> build -> git commit -> git push(non-fatal) -> alert
alerts.py          Telegram alert on failure / unhealthy run (no-op if unset)
index.html/app.js/style.css   static frontend (reads ./data/)
run_daily.bat / install_task.ps1   Windows Task Scheduler automation
data/
  current/<id>.json   current constituents {symbol,name,isin}; overwritten each run
  changes.jsonl       append-only {date,index,type,added,removed}; only on a diff
  meta.json           last-run time + per-index status + health
  indices.json        registry id -> {name,category}
  summary.json        precomputed payload the frontend loads
```

## Setup

```bash
python -m pip install -r requirements.txt   # pykrx pinned (legacy/optional); stdlib+requests used
```

Optional Telegram alerts — copy `.env.example` to `.env` and fill:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Run

```bash
python fetcher.py            # full fetch of all allow-listed indices
python fetcher.py --quick    # smoke test (static indices + 3 sectors)
python build_site.py         # regenerate data/summary.json
python run_daily.py          # full daily pipeline (fetch+build+commit+push+alert)
```

Preview the site locally:
```bash
python -m http.server 8000   # then open http://localhost:8000/
```

## Automate (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File .\install_task.ps1            # daily 13:00 IST
powershell -ExecutionPolicy Bypass -File .\install_task.ps1 -Remove    # uninstall
Start-ScheduledTask -TaskName KoreaIndexTracker                        # run now
```

## Publish (GitHub Pages)

```bash
gh repo create <owner>/korea-index-tracker --public --source . --push
# then enable Pages (Settings → Pages → Deploy from branch → main / root),
# or:  gh api -X POST repos/<owner>/korea-index-tracker/pages -f source.branch=main -f source.path=/
```

## Correctness guards

- **Snapshot guard** — skip diff+write for any index whose new fetch is empty or
  shrinks > `GUARD_DROP_FRACTION` (40 %) vs the last snapshot; mark guarded and (if
  systemic) alert. Protects against silent source breakage.
- **First-run baseline** — run 1 seeds `current/` and one `{type:"initial"}` per
  index, no diff.
- **Push isolation** — commit always; push is separate and non-fatal.
- **No git churn** — `current/<id>.json` has no timestamps and is sorted by symbol,
  so it only changes on a real membership change.
