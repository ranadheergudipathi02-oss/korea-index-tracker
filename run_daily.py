"""
Daily entrypoint for the Static Korea Index Tracker (Task Scheduler runs this).

  fetch (fetcher.main) -> build_site -> git commit -> git push -> alert-if-needed

Design rules honored:
  - git push is a SEPARATE, non-fatal step (commit can succeed even if push fails).
  - Telegram alert ONLY on a fetch failure or an unhealthy run, never on a normal
    zero-change run.
  - Exit non-zero only on a hard fetch failure (so Task Scheduler shows the error).
"""
import krx_env  # utf-8 console + .env
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import config
import fetcher
import build_site
import alerts

KST = timezone(timedelta(hours=9))
ROOT = config.ROOT


def git(*args, check=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if out:
        print(f"[git {' '.join(args)}] {out}")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out}")
    return r.returncode, out


def main():
    print(f"=== run_daily {datetime.now(KST).isoformat()} ===")

    # 1) FETCH (hard-fail -> alert + non-zero exit)
    try:
        meta = fetcher.main()
    except Exception as e:
        alerts.alert_failure("fetch", repr(e))
        print(f"FATAL fetch error: {e!r}")
        return 1

    # 2) BUILD SITE SUMMARY
    try:
        build_site.main()
    except Exception as e:
        alerts.alert_failure("build_site", repr(e))
        print(f"build_site error (continuing to commit): {e!r}")

    # 3) COMMIT (fine to commit; push is separate)
    date = meta.get("detect_date")
    c = meta.get("counts", {})
    msg = (f"data: {date} | changed={c.get('changed',0)} new={c.get('initial',0)} "
           f"guarded={c.get('guarded',0)} err={c.get('error',0)}")
    git("add", "-A")
    code, out = git("commit", "-m", msg)
    nothing_to_commit = "nothing to commit" in out
    committed = (code == 0) and not nothing_to_commit
    if committed:
        print(f"committed: {msg}")
    elif nothing_to_commit:
        print("no data changes to commit")

    # 4) PUSH (ISOLATED, NON-FATAL)
    if committed:
        try:
            code, out = git("push")
            if code != 0:
                print(f"push failed (non-fatal): {out}")
        except Exception as e:
            print(f"push exception (non-fatal): {e!r}")

    # 5) HEALTH ALERT (not on zero-change; only on unhealthy)
    if meta.get("unhealthy"):
        alerts.alert_unhealthy(meta)

    print("=== run_daily done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
