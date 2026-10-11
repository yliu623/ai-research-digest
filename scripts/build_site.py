#!/usr/bin/env python3
"""Build the static archive site into _site/ (run by GitHub Actions; also works locally).

Usage: python3 scripts/build_site.py [--out _site] [--releases releases.json]
  releases.json: output of `gh release list --json tagName` (optional). Audio for a day is linked from
  _site/audio/briefing-<date>.mp3 when that file exists (the workflow downloads the last 30 days),
  otherwise from the GitHub Release asset when the audio-<date> release exists.
"""
import argparse
import glob
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--releases", default="")
    a = ap.parse_args()
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    tags = set()
    if a.releases and os.path.exists(a.releases):
        with open(a.releases) as f:
            tags = {r["tagName"] for r in json.load(f)}

    os.makedirs(a.out, exist_ok=True)
    for name in os.listdir(os.path.join(ROOT, "site")):
        shutil.copy(os.path.join(ROOT, "site", name), os.path.join(a.out, name))

    days = []
    for path in sorted(glob.glob(os.path.join(ROOT, "digests", "digest-*.json")), reverse=True):
        with open(path) as f:
            d = json.load(f)
        date = d["date"]
        local = os.path.join(a.out, "audio", f"briefing-{date}.mp3")
        if os.path.exists(local):
            audio = f"audio/briefing-{date}.mp3"
        elif f"audio-{date}" in tags:
            audio = f"https://github.com/{cfg['repo']}/releases/download/audio-{date}/briefing-{date}.mp3"
        else:
            audio = None
        days.append({"date": date, "sections": d["sections"], "footnote": d.get("footnote", ""),
                     "briefing": d.get("briefing") or [], "audio": audio})
    with open(os.path.join(a.out, "all.json"), "w") as f:
        json.dump({"days": days}, f, ensure_ascii=False, separators=(",", ":"))
    n = sum(len(s["items"]) for d in days for s in d["sections"])
    print(f"built {a.out}: {len(days)} days, {n} items, {sum(1 for d in days if d['audio'])} with audio")


if __name__ == "__main__":
    main()
