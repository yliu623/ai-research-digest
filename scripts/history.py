#!/usr/bin/env python3
"""Dedup history for the AI Research Digest.

Usage:
  python3 scripts/history.py window              # prints window start (YYYY-MM-DD)
  python3 scripts/history.py dedup OUT.json      # writes {"urls":[...], "titles":[...]} for other scripts
  python3 scripts/history.py merge DIGEST.json   # adds the digest's items to data/seen-items.json
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN = os.path.join(ROOT, "data", "seen-items.json")


def load_seen():
    if not os.path.exists(SEEN):
        return []
    with open(SEEN) as f:
        return json.load(f)


def norm_url(u):
    u = u.strip().split("#")[0]
    u = re.sub(r"^http://", "https://", u)
    u = re.sub(r"(arxiv\.org/(?:abs|pdf)/\d{4}\.\d{4,5})v\d+", r"\1", u)
    return u.rstrip("/")


def audio_id(url):
    """Stable short id for a paper's audio file and its site anchor (#p-<id>)."""
    return hashlib.sha1(norm_url(url).encode()).hexdigest()[:10]


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def window_start(seen):
    dates = [e["date_sent"] for e in seen if e.get("date_sent")]
    if not dates:
        return (dt.date.today() - dt.timedelta(days=7)).isoformat()
    return max(dates)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    seen = load_seen()
    if cmd == "window":
        print(window_start(seen))
    elif cmd == "dedup":
        out = {"urls": sorted({norm_url(e["url"]) for e in seen}),
               "titles": sorted({norm_title(e.get("title", "")) for e in seen if e.get("title")})}
        with open(sys.argv[2], "w") as f:
            json.dump(out, f)
        print(f"dedup: {len(out['urls'])} urls, {len(out['titles'])} titles -> {sys.argv[2]}")
    elif cmd == "merge":
        with open(sys.argv[2]) as f:
            digest = json.load(f)
        have = {norm_url(e["url"]) for e in seen}
        added = []
        for sec in digest["sections"]:
            for it in sec["items"]:
                if norm_url(it["url"]) in have:
                    continue
                have.add(norm_url(it["url"]))
                added.append({"url": it["url"], "title": it["title"], "date_sent": digest["date"]})
        seen.extend(added)
        with open(SEEN, "w") as f:
            json.dump(seen, f, indent=1, ensure_ascii=False)
        print(f"merged {len(added)} new items; history now {len(seen)}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
