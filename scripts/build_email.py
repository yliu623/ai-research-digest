#!/usr/bin/env python3
"""Render a digest as an email: plain text + inline-styled HTML (no <style> block).

Usage: python3 scripts/build_email.py digests/digest-YYYY-MM-DD.json OUTDIR
Writes OUTDIR/email-YYYY-MM-DD.txt and OUTDIR/email-YYYY-MM-DD.html and prints both paths.
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK = "#1a1a1a"
MUTED = "#6b7280"
ACCENT = "#1d4ed8"
LINE = "#e5e7eb"
NOTEBOOKLM = "https://notebooklm.google.com/"


def config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def split_tag(desc):
    m = re.search(r"\s*\[([^\]]+)\]\s*$", desc)
    return (desc[:m.start()].strip(), m.group(1)) if m else (desc.strip(), "")


def build_text(d, day_url):
    out = [f"Daily AI Research Digest — {d['date']}", f"Web archive: {day_url}"]
    if d.get("note"):
        out.append(d["note"])
    if d.get("briefing"):
        out.append(f"Audio briefing (2 voices): {day_url}")
    out.append("")
    for s in d["sections"]:
        out += [s["name"], "-" * 40]
        if not s["items"]:
            out += ["Nothing new in this window.", ""]
            continue
        for it in s["items"]:
            body, tag = split_tag(it["desc"])
            out.append(f"- {it['title']} — {it['url']}")
            out.append(f"  {body} [{tag}]" if tag else f"  {body}")
            if it.get("fulltext") and it["fulltext"] != it["url"]:
                out.append(f"  Full text: {it['fulltext']}")
            out.append("")
    if d.get("footnote"):
        out += ["—", d["footnote"]]
    return "\n".join(out)


def build_html(d, day_url):
    e = html.escape
    p = [f'<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;'
         f'color:{INK};max-width:720px;margin:0 auto;padding:8px 4px;line-height:1.5;">',
         f'<h1 style="font-size:22px;margin:0 0 4px;color:{INK};">🗞️ Daily AI Research Digest</h1>',
         f'<p style="font-size:13px;color:{MUTED};margin:0 0 6px;">{e(d["date"])} · New papers &amp; news on AI in '
         f'economics, finance, and operations/supply chain.</p>',
         f'<p style="font-size:13px;margin:0 0 18px;"><a href="{e(day_url, quote=True)}" '
         f'style="color:{ACCENT};text-decoration:none;font-weight:600;">View on the web archive →</a>']
    if d.get("note"):
        p.insert(3, f'<p style="font-size:14px;margin:0 0 10px;padding:8px 10px;background:#fff7ed;border:1px solid #fed7aa;'
                    f'border-radius:6px;color:{INK};">{e(d["note"])}</p>')
    if d.get("briefing"):
        p.append(f' &nbsp;·&nbsp; <a href="{e(day_url, quote=True)}" style="color:{ACCENT};text-decoration:none;'
                 f'font-weight:600;">🎧 Listen to the 2-voice briefing</a>')
    p.append("</p>")
    p.append(f'<p style="font-size:12px;color:{MUTED};margin:0 0 18px;background:#f8fafc;border:1px solid {LINE};'
             f'border-radius:6px;padding:8px 10px;">🎧 To hear any paper as a podcast: on the '
             f'<a href="{e(day_url, quote=True)}" style="color:{ACCENT};">web archive</a> click its NotebookLM button '
             f'(it copies the link and opens NotebookLM), add it as a Website source, then click <b>Audio Overview</b>. '
             f'Or copy a <b>Full text</b> link here and paste it into '
             f'<a href="{NOTEBOOKLM}" style="color:{ACCENT};">NotebookLM</a>.</p>')
    for s in d["sections"]:
        p.append(f'<h2 style="font-size:16px;margin:26px 0 10px;padding-bottom:5px;border-bottom:2px solid {LINE};'
                 f'color:{INK};">{e(s["name"])} <span style="color:{MUTED};font-weight:normal;font-size:13px;">'
                 f'({len(s["items"])})</span></h2>')
        if not s["items"]:
            p.append(f'<p style="font-size:14px;color:{MUTED};margin:0 0 12px;">Nothing new in this window.</p>')
            continue
        # Kept compact: Gmail clips HTML bodies over ~100 KB.
        for it in s["items"]:
            body, tag = split_tag(it["desc"])
            ft = it.get("fulltext")
            full = f' · <a href="{e(ft, quote=True)}" style="color:{MUTED}">Full text</a>' if ft and ft != it["url"] else ""
            p.append(f'<p style="margin:0 0 14px;font-size:14px;color:#333">'
                     f'<a href="{e(it["url"], quote=True)}" style="color:{ACCENT};font-weight:700;font-size:15px;'
                     f'text-decoration:none">{e(it["title"])}</a><br>{e(body)}<br>'
                     f'<span style="font-size:12px;color:{MUTED}">{e(tag)}{full}</span></p>')
    if d.get("footnote"):
        p.append(f'<p style="margin-top:28px;padding-top:12px;border-top:1px solid {LINE};color:{MUTED};'
                 f'font-size:12px;">{e(d["footnote"])}</p>')
    p.append("</div>")
    return "\n".join(p)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        d = json.load(f)
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    day_url = config()["site_url"].rstrip("/") + f"/#{d['date']}"
    tpath = os.path.join(outdir, f"email-{d['date']}.txt")
    hpath = os.path.join(outdir, f"email-{d['date']}.html")
    with open(tpath, "w") as f:
        f.write(build_text(d, day_url))
    with open(hpath, "w") as f:
        f.write(build_html(d, day_url))
    print("TEXT", tpath)
    print("HTML", hpath)


if __name__ == "__main__":
    main()
