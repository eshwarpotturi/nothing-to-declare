"""Shared helpers: config, timestamped logging, cached HTTP, small thread pool."""
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
CACHE = PRIVATE / "cache"
DATA = PRIVATE / "data"
RESULTS = PRIVATE / "results"
PUBLIC = ROOT / "docs" / "data"
for d in (CACHE, DATA, RESULTS, PUBLIC):
    d.mkdir(parents=True, exist_ok=True)


def cfg():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        c = yaml.safe_load(f)
    with open(ROOT / c["papers"]["journals_file"], encoding="utf-8") as f:
        c["papers"]["journals"] = yaml.safe_load(f)["journals"]
    return c


def log(msg, done=None, total=None):
    prog = f" [{done}/{total}]" if total else ""
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}{prog} {msg}", flush=True)


_session = requests.Session()


def get(url, params=None, as_json=True, retries=4):
    """GET with an on-disk cache keyed by URL+params, so re-runs are free."""
    key = hashlib.sha1((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = CACHE / key[:2] / (key + (".json" if as_json else ".txt"))
    if path.exists():
        try:
            txt = path.read_text(encoding="utf-8")
            return json.loads(txt) if as_json else txt
        except (UnicodeDecodeError, ValueError):
            path.unlink()  # unreadable or half-written cache file: fetch it again
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            path.parent.mkdir(exist_ok=True)
            path.write_text(r.text, encoding="utf-8")
            return r.json() if as_json else r.text
        except (requests.RequestException, ValueError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 3)


def pool(items, fn, workers, label):
    """Run fn over items in threads, logging done/total every ~5%."""
    out, total = [], len(items)
    step = max(1, total // 20)
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                out.append(f.result())
            except Exception as e:
                log(f"{label}: error {e!r}")
            if i % step == 0 or i == total:
                log(label, i, total)
    return out


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def env_token(name):
    if os.environ.get(name):
        return os.environ[name]
    envf = PRIVATE / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return None
