#!/usr/bin/env python3
"""Build the static archive site into _site/ (run by GitHub Actions; also works locally).

Usage: python3 scripts/build_site.py [--out _site] [--releases releases.json]
  releases.json: [{"tag", "assets": [names]}] from the GitHub releases API (optional). Each audio file (the
  day's briefing-<date>.mp3 and each paper's p-<id>.mp3) is served from _site/audio/ when the workflow
  downloaded it (last 14 days), otherwise from its GitHub Release asset.
"""
import argparse
import glob
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from history import audio_id  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--releases", default="")
    a = ap.parse_args()
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    assets = {}  # release tag -> set of asset names
    if a.releases and os.path.exists(a.releases):
        with open(a.releases) as f:
            for r in json.load(f):
                assets[r.get("tag") or r.get("tagName")] = set(r.get("assets") or [])

    def audio_url(date, name):
        if os.path.exists(os.path.join(a.out, "audio", name)):
            return f"audio/{name}"
        if name in assets.get(f"audio-{date}", ()):
            return f"https://github.com/{cfg['repo']}/releases/download/audio-{date}/{name}"
        return None

    os.makedirs(a.out, exist_ok=True)
    for name in os.listdir(os.path.join(ROOT, "site")):
        shutil.copy(os.path.join(ROOT, "site", name), os.path.join(a.out, name))

    days = []
    for path in sorted(glob.glob(os.path.join(ROOT, "digests", "digest-*.json")), reverse=True):
        with open(path) as f:
            d = json.load(f)
        date = d["date"]
        sections = []
        for s in d["sections"]:
            items = []
            for it in s["items"]:
                it = {k: v for k, v in it.items() if k != "podcast"}  # scripts stay in the repo, not the page
                it["aid"] = audio_id(it["url"])
                it["audio"] = audio_url(date, f"p-{it['aid']}.mp3")
                items.append(it)
            sections.append({"name": s["name"], "items": items})
        days.append({"date": date, "sections": sections, "footnote": d.get("footnote", ""),
                     "briefing": d.get("briefing") or [], "audio": audio_url(date, f"briefing-{date}.mp3")})
    with open(os.path.join(a.out, "all.json"), "w") as f:
        json.dump({"days": days}, f, ensure_ascii=False, separators=(",", ":"))
    n = sum(len(s["items"]) for d in days for s in d["sections"])
    pods = sum(1 for d in days for s in d["sections"] for it in s["items"] if it["audio"])
    print(f"built {a.out}: {len(days)} days, {n} items, {sum(1 for d in days if d['audio'])} briefings, {pods} paper audios")


if __name__ == "__main__":
    main()
