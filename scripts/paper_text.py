#!/usr/bin/env python3
"""Print a condensed plain-text version of a paper PDF for writing its audio explainer.

Usage: python3 scripts/paper_text.py <pdf-url> [--head 14000] [--tail 5000]
Needs pypdf (`pip install -q pypdf`). Prints the opening (abstract, intro, data/method) and the end
(results/conclusion) with whitespace collapsed. Exits 1 if the PDF can't be fetched or read.
"""
import argparse
import io
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--head", type=int, default=14000)
    ap.add_argument("--tail", type=int, default=5000)
    a = ap.parse_args()
    try:
        from pypdf import PdfReader
        req = urllib.request.Request(a.url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            raise ValueError("not a PDF (paywall or HTML page?)")
        reader = PdfReader(io.BytesIO(data))
        text = " ".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:  # noqa: BLE001
        print(f"could not read {a.url}: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    text = re.sub(r"\s+", " ", text).strip()
    # Drop the reference list, which is long and useless for an explainer.
    m = re.search(r"\b(References|REFERENCES|Bibliography)\b(?!.*\b(References|REFERENCES)\b)", text)
    if m and m.start() > len(text) * 0.5:
        text = text[:m.start()]
    if len(text) <= a.head + a.tail:
        print(text)
    else:
        print(text[:a.head] + "\n\n[…middle omitted…]\n\n" + text[-a.tail:])


if __name__ == "__main__":
    main()
