"""
Telegram alerting. No-op unless TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
(in .env or the real environment). Alerts fire ONLY on a fetch failure or an
unhealthy run (most indices failed/guarded = silent-block signal) — never on a
normal zero-membership-change run.
"""
import os
import json
import urllib.request
import urllib.parse


def _send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[alerts] Telegram not configured — skipping alert.")
        return False
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            ok = json.loads(r.read().decode()).get("ok", False)
        print(f"[alerts] Telegram sent: {ok}")
        return ok
    except Exception as e:
        print(f"[alerts] Telegram send failed (non-fatal): {e!r}")
        return False


def alert_failure(stage, detail):
    _send(f"🔴 <b>Korea Index Tracker FAILED</b>\nStage: {stage}\n{detail}")


def alert_unhealthy(meta):
    c = meta.get("counts", {})
    _send("🟠 <b>Korea Index Tracker — unhealthy run</b>\n"
          f"detect_date {meta.get('detect_date')}\n"
          f"guarded={c.get('guarded',0)} error={c.get('error',0)} "
          f"of {meta.get('total_indices',0)} indices.\n"
          "Possible silent block / source change — check the fetcher.")
