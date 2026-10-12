#!/usr/bin/env python3
"""Sanity checks for a digest before it is sent.

Usage: python3 scripts/check_digest.py digests/digest-YYYY-MM-DD.json --since YYYY-MM-DD
Run BEFORE `history.py merge` (it also checks nothing was already sent).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from history import load_seen, norm_url  # noqa: E402
from fetch_sources import PAPER_LOOKBACK_DAYS  # noqa: E402

SECTIONS = ["📊 Economics (NBER / SSRN / arXiv)",
            "💵 Finance (SSRN / NBER / arXiv q-fin)",
            "📦 Operations & Supply Chain (INFORMS: Management Science, M&SOM, Operations Research)",
            "📰 News (NYT / WSJ / Bloomberg / FT / Washington Post / Economist)"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("digest")
    ap.add_argument("--since", required=True)
    a = ap.parse_args()
    with open(a.digest) as f:
        d = json.load(f)
    since = dt.date.fromisoformat(a.since)
    until = dt.date.fromisoformat(d["date"])
    errs = []
    names = [s["name"] for s in d["sections"]]
    if names != SECTIONS:
        errs.append(f"section names/order differ: {names}")
    seen = {norm_url(e["url"]) for e in load_seen()}
    urls = set()
    n = 0
    for s in d["sections"]:
        for it in s["items"]:
            n += 1
            t = it.get("title", "")[:60]
            for k in ("title", "url", "desc"):
                if not it.get(k):
                    errs.append(f"missing {k}: {t}")
            u = norm_url(it.get("url", ""))
            if not u.startswith("https://"):
                errs.append(f"non-https url: {u}")
            if u in urls:
                errs.append(f"duplicate url: {u}")
            if u in seen:
                errs.append(f"already sent: {u}")
            urls.add(u)
            m = re.search(r"\[([^\]]*?)(\d{4}-\d{2}-\d{2})\]\s*$", it.get("desc", ""))
            date = it.get("date") or (m.group(2) if m else None)
            if not m:
                errs.append(f"desc lacks trailing [source, date] tag: {t}")
            if not date:
                errs.append(f"no date: {t}")
            else:
                # papers may predate the window by the fetcher's lookback (publication lag); news may not
                lo = since if s["name"].startswith("📰") else since - dt.timedelta(days=PAPER_LOOKBACK_DAYS)
                if not (lo <= dt.date.fromisoformat(date) <= until):
                    errs.append(f"date {date} outside window {lo}..{until}: {t}")
    for i, line in enumerate(d.get("briefing") or []):
        if line.get("speaker") not in ("A", "B") or not line.get("text"):
            errs.append(f"briefing line {i} malformed")
    pods = 0
    for s in d["sections"]:
        for it in s["items"]:
            pod = it.get("podcast")
            if pod is None:
                continue
            pods += 1
            if s["name"].startswith("📰"):
                errs.append(f"news items don't get podcasts: {it['title'][:60]}")
            words = sum(len(x.get("text", "").split()) for x in pod)
            if any(x.get("speaker") not in ("A", "B") or not x.get("text") for x in pod):
                errs.append(f"podcast malformed: {it['title'][:60]}")
            elif not 150 <= words <= 600:
                errs.append(f"podcast {words} words (want ~200-450): {it['title'][:60]}")
    if errs:
        print("FAIL\n  " + "\n  ".join(errs))
        sys.exit(1)
    words = sum(len(x["text"].split()) for x in d.get("briefing") or [])
    print(f"OK: {n} items, {pods} paper podcasts, briefing {words} words, window {since}..{until}")


if __name__ == "__main__":
    main()
