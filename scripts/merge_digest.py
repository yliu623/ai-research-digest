#!/usr/bin/env python3
"""Append a same-day update into the day's digest file.

Usage: python3 scripts/merge_digest.py digests/digest-YYYY-MM-DD.json /tmp/digest-new.json
Items from the update are appended per section (skipping URLs already in the file, newest first within
each section), the update's briefing is used only if the day had none, and the footnotes are joined.
"""
import json
import re
import sys


def main():
    day_path, new_path = sys.argv[1], sys.argv[2]
    with open(day_path) as f:
        day = json.load(f)
    with open(new_path) as f:
        new = json.load(f)
    assert day["date"] == new["date"], "dates differ"
    by_emoji = {s["name"][:1]: s for s in day["sections"]}
    added = 0
    for s in new["sections"]:
        target = by_emoji.get(s["name"][:1])
        if target is None:
            day["sections"].append(s)
            added += len(s["items"])
            continue
        target["name"] = s["name"]
        have = {it["url"] for it in target["items"]}
        fresh = [it for it in s["items"] if it["url"] not in have]
        added += len(fresh)

        def key(it):
            m = re.search(r"(\d{4}-\d{2}-\d{2})\]?\s*$", it.get("desc", ""))
            return it.get("date") or (m.group(1) if m else "")
        target["items"] = sorted(target["items"] + fresh, key=key, reverse=True)
    if new.get("briefing") and not day.get("briefing"):
        day["briefing"] = new["briefing"]  # keep the day's main briefing; an update only fills a gap
    if new.get("footnote"):
        day["footnote"] = (day.get("footnote", "") + " — Update: " + new["footnote"]).strip(" —")
    with open(day_path, "w") as f:
        json.dump(day, f, indent=1, ensure_ascii=False)
    print(f"merged {added} items into {day_path}")


if __name__ == "__main__":
    main()
