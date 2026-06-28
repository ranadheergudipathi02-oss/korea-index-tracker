"""Tiny dependency-free .env loader + UTF-8 console setup.

Imported by every script so KRX_ID/KRX_PW reach pykrx (which reads them from
os.environ at import time) and so Hangul prints don't crash the cp1252 console.
"""
import os
import sys


def _force_utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_env(path=None):
    """Load KEY=VALUE lines from a .env file into os.environ (does not override
    variables already set in the real environment). Returns dict of what it set."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    loaded = {}
    if not os.path.exists(path):
        return loaded
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
                loaded[key] = val
    return loaded


# Run on import: console first, then env (so pykrx sees creds before its import).
_force_utf8_console()
load_env()
