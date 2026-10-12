#!/usr/bin/env python3
"""Collect in-window candidates for the AI Research Digest from sources with machine-readable dates.

Usage: python3 scripts/fetch_sources.py --since YYYY-MM-DD [--until YYYY-MM-DD] [--out candidates.json]

Sources: arXiv export API (econ.* + q-fin.*), Crossref (INFORMS journals, published-online date),
NBER (API listing + paper-page issue date), NYT daily sitemaps + RSS, Economist RSS, Washington Post RSS, WSJ RSS + news sitemap, Bloomberg RSS, FT RSS.
SSRN is not covered here (no machine-readable feed); the agent searches it separately.

Every candidate has a verified `date`, matches the AI keyword list, and is not already in
data/seen-items.json. News dates fall inside [since, until]; paper sources look back PAPER_LOOKBACK_DAYS
before `since` because they become visible days after their submission / online date. Relevance judgment
is left to the agent.
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from history import load_seen, norm_title, norm_url  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
API_UA = "ai-research-digest/1.0 (https://github.com; mailto:ai-research-digest@agentmail.to)"

# Phrases are matched case-insensitively; acronyms case-sensitively as whole words.
PHRASES = ["artificial intelligence", "agentic", "ai agent", "ai agents", "large language model",
           "large language models", "generative ai", "foundation model", "foundation models",
           "tabular foundation model", "machine learning", "deep learning", "reinforcement learning",
           "neural network", "neural networks", "transformer", "transformers", "chatbot", "chatbots",
           "language model", "language models", "agent-based", "llm-based", "openai", "chatgpt",
           "anthropic", "data center", "data centers", "data centre"]
ACRONYMS = ["AI", "LLM", "LLMs", "GPT", "GenAI", "AGI"]
WORDS_CI = ["agent", "agents"]  # broad on purpose (spec); the agent filters principal-agent noise
_PHRASE_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in PHRASES) + r")\b", re.I)
_ACRO_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(ACRONYMS) + r")(?![A-Za-z])")
_WORD_RE = re.compile(r"\b(" + "|".join(WORDS_CI) + r")\b", re.I)

ARXIV_KW = ('abs:"artificial intelligence" OR abs:AI OR abs:agentic OR abs:"AI agent" OR abs:agent '
            'OR abs:LLM OR abs:LLMs OR abs:"large language model" OR abs:"large language models" '
            'OR abs:"generative AI" OR abs:"foundation model" OR abs:"tabular foundation model" '
            'OR abs:"machine learning" OR abs:"deep learning" OR abs:"reinforcement learning" '
            'OR abs:"neural network" OR abs:transformer OR abs:chatbot OR abs:GPT '
            'OR ti:LLM OR ti:AI OR ti:agent OR ti:agents')
ARXIV_CATS = {
    "econ": ["econ.GN", "econ.EM", "econ.TH"],
    "qfin": ["q-fin.CP", "q-fin.EC", "q-fin.GN", "q-fin.MF", "q-fin.PM", "q-fin.PR",
             "q-fin.RM", "q-fin.ST", "q-fin.TR"],
}
PAPER_LOOKBACK_DAYS = 7
INFORMS_JOURNALS = {"Management Science", "Manufacturing & Service Operations Management",
                    "Operations Research"}
NEWS_KW = re.compile(r"(?<![A-Za-z])(A\.I\.|AI|OpenAI|ChatGPT|Nvidia|Anthropic|chatbots?|data cent(er|re)s?|"
                     r"artificial intelligence|machine learning|large language|generative|automation|robots?|"
                     r"agentic|algorithm)(?![A-Za-z])", re.I)


def kw_match(text):
    return bool(_PHRASE_RE.search(text) or _ACRO_RE.search(text) or _WORD_RE.search(text))


def get(url, ua=UA, timeout=45, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            # 4xx (blocked host, missing feed) won't fix itself; only retry rate limits and server errors.
            if e.code != 429 and e.code < 500:
                raise
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        if i < tries - 1:
            time.sleep(3 * (i + 1))
    raise last


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ---------------------------------------------------------------- arXiv
def fetch_arxiv(group, since, until):
    cats = " OR ".join(f"cat:{c}" for c in ARXIV_CATS[group])
    q = f"({cats}) AND ({ARXIV_KW}) AND submittedDate:[{since:%Y%m%d}0000 TO {until:%Y%m%d}2359]"
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    out, start = [], 0
    while True:
        url = ("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending",
             "start": start, "max_results": 100}))
        root = ET.fromstring(get(url, ua=API_UA, timeout=90))
        entries = root.findall("a:entry", ns)
        for e in entries:
            aid = e.find("a:id", ns).text.rsplit("/abs/", 1)[-1]
            aid = re.sub(r"v\d+$", "", aid)
            title = strip_tags(e.find("a:title", ns).text)
            abstract = strip_tags(e.find("a:summary", ns).text)
            pub = e.find("a:published", ns).text[:10]
            cats_ = [c.get("term") for c in e.findall("a:category", ns)]
            primary = e.find("arxiv:primary_category", ns)
            out.append({"source": "arXiv", "group": group, "title": title,
                        "url": f"https://arxiv.org/abs/{aid}", "fulltext": f"https://arxiv.org/pdf/{aid}",
                        "date": pub, "categories": cats_,
                        "primary": primary.get("term") if primary is not None else cats_[0],
                        "abstract": abstract})
        total = int(root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults").text)
        start += 100
        if start >= total or not entries:
            break
        time.sleep(3)
    return out


# ---------------------------------------------------------------- INFORMS via Crossref
def fetch_informs(since, until):
    out, cursor = [], "*"
    while True:
        url = ("https://api.crossref.org/works?" + urllib.parse.urlencode({
            "filter": f"prefix:10.1287,from-online-pub-date:{since},until-online-pub-date:{until}",
            "select": "DOI,title,abstract,container-title,published-online,type",
            "rows": 200, "cursor": cursor}))
        msg = json.loads(get(url, ua=API_UA))["message"]
        for it in msg["items"]:
            journal = html.unescape((it.get("container-title") or [""])[0])
            doi = it["DOI"]
            if journal not in INFORMS_JOURNALS or doi.endswith(".cd") or it.get("type") != "journal-article":
                continue
            title = strip_tags((it.get("title") or [""])[0])
            abstract = strip_tags(it.get("abstract", ""))
            if not kw_match(title + " " + abstract):
                continue
            parts = it["published-online"]["date-parts"][0] + [1, 1]
            date = dt.date(parts[0], parts[1], parts[2]).isoformat()
            out.append({"source": "INFORMS", "journal": journal, "title": title,
                        "url": f"https://pubsonline.informs.org/doi/{doi}", "date": date,
                        "abstract": abstract})
        cursor = msg.get("next-cursor")
        if not msg["items"] or not cursor:
            break
        time.sleep(1)
    return out


# ---------------------------------------------------------------- NBER
_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def fetch_nber(since, until, seen_urls):
    out, page, stale_pages = [], 1, 0
    first_month = (since.year, since.month)
    while page <= 8 and stale_pages < 1:
        url = ("https://www.nber.org/api/v1/working_page_listing/contentType/working_paper/_/_/search?"
               f"page={page}&perPage=100&sortBy=public_date")
        results = json.loads(get(url))["results"]
        if not results:
            break
        in_range = 0
        for r in results:
            m = re.match(r"(\w+) (\d{4})", r.get("displaydate") or "")
            if not m or (int(m.group(2)), _MONTHS.get(m.group(1), 0)) < first_month:
                continue
            in_range += 1
            link = "https://www.nber.org" + r["url"]
            text = r["title"] + " " + strip_tags(r.get("abstract", ""))
            if norm_url(link) in seen_urls or not kw_match(text):
                continue
            page_html = get(link)
            dm = re.search(r'citation_publication_date" content="(\d{4})/(\d{2})/(\d{2})', page_html)
            if not dm:
                continue
            date = dt.date(*map(int, dm.groups()))
            if not (since <= date <= until):
                continue
            ab = re.search(r'page-header__intro-inner">\s*(.*?)</div>', page_html, re.S)
            pdf = re.search(r'citation_pdf_url" content="([^"]+)"', page_html)
            out.append({"source": "NBER", "title": strip_tags(r["title"]), "url": link,
                        "fulltext": pdf.group(1) if pdf else link, "date": date.isoformat(),
                        "abstract": strip_tags(ab.group(1)) if ab else strip_tags(r.get("abstract", ""))})
            time.sleep(1)
        stale_pages = stale_pages + 1 if in_range == 0 else 0
        page += 1
    return out


# ---------------------------------------------------------------- News
def fetch_nyt(since, until):
    out, seen = [], set()
    d, days, failed, last_err = since, 0, 0, None
    while d <= until:
        days += 1
        try:
            page = get(f"https://www.nytimes.com/sitemap/{d:%Y/%m/%d}/")
        except Exception as e:  # noqa: BLE001
            failed, last_err = failed + 1, e
            d += dt.timedelta(days=1)
            continue
        pat = rf'<a href="(https://www\.nytimes\.com/{d:%Y/%m/%d}/[^"]+)"[^>]*>([^<]+)</a>'
        for link, title in re.findall(pat, page):
            title = html.unescape(title).strip()
            section = link.split("/")[6] if len(link.split("/")) > 7 else ""
            if link in seen or not NEWS_KW.search(title + " " + link.replace("-", " ")):
                continue
            if section in {"crosswords", "learning", "pageoneplus", "briefing", "podcasts", "realestate",
                           "style", "arts", "movies", "theater", "books", "fashion", "travel", "sports",
                           "dining", "well", "t-magazine", "obituaries", "nyregion", "insider"}:
                continue
            seen.add(link)
            out.append({"source": "NYT", "section": section, "title": title, "url": link,
                        "date": d.isoformat(), "abstract": ""})
        d += dt.timedelta(days=1)
        time.sleep(0.5)
    if days and failed == days:
        raise RuntimeError(f"all {days} NYT sitemap pages failed: {last_err}")
    # RSS gives descriptions for recent items
    for feed in ["Technology", "Business", "Economy", "YourMoney", "DealBook"]:
        try:
            for it in parse_rss(get(f"https://rss.nytimes.com/services/xml/rss/nyt/{feed}.xml")):
                for c in out:
                    if c["url"] == it["url"].split("?")[0]:
                        c["abstract"] = it["abstract"]
        except Exception:  # noqa: BLE001
            pass
    return out


def parse_rss(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            date = email.utils.parsedate_to_datetime(pub).date() if pub else None
        except Exception:  # noqa: BLE001
            date = None
        items.append({"title": strip_tags(it.findtext("title")), "url": link, "date": date,
                      "abstract": strip_tags(it.findtext("description"))})
    return items


def fetch_rss_news(source, feeds, since, until):
    out, seen = [], set()
    errors = []
    for feed in feeds:
        try:
            items = parse_rss(get(feed))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{feed}: {e}")
            continue
        for it in items:
            if not it["date"] or not (since <= it["date"] <= until):
                continue
            url = it["url"].split("?")[0]
            if url in seen or not NEWS_KW.search(it["title"] + " " + it["abstract"]):
                continue
            seen.add(url)
            out.append({"source": source, "title": it["title"], "url": url,
                        "date": it["date"].isoformat(), "abstract": it["abstract"]})
    if errors and len(errors) == len(feeds):
        raise RuntimeError("; ".join(errors))
    return out


ECONOMIST_FEEDS = [f"https://www.economist.com/{s}/rss.xml" for s in
                   ["finance-and-economics", "business", "science-and-technology", "leaders", "briefing",
                    "united-states", "china", "international", "the-world-this-week"]]
WSJ_FEEDS = [f"https://feeds.content.dowjones.io/public/rss/{s}" for s in
             ["RSSWSJD", "socialeconomyfeed", "RSSMarketsMain", "WSJcomUSBusiness"]]
BLOOMBERG_FEEDS = [f"https://feeds.bloomberg.com/{s}/news.rss" for s in
                   ["technology", "markets", "economics", "business", "industries"]]
FT_FEEDS = [f"https://www.ft.com/{s}?format=rss" for s in
            ["artificial-intelligence", "technology", "companies", "markets", "global-economy", "us-economy",
             "financials"]]
WAPO_FEEDS = ["https://feeds.washingtonpost.com/rss/business",
              "https://feeds.washingtonpost.com/rss/business/technology",
              "https://feeds.washingtonpost.com/rss/business/economy"]


def fetch_wsj(since, until):
    """WSJ RSS (with teasers) plus its Google News sitemap for extra discovery; WSJ URLs carry no date."""
    out = fetch_rss_news("WSJ", WSJ_FEEDS, since, until)
    have = {c["url"] for c in out}
    try:
        page = get("https://www.wsj.com/wsjsitemaps/wsj_google_news.xml")
        for block in re.findall(r"<url>(.*?)</url>", page, re.S):
            loc = re.search(r"<loc>([^<]+)</loc>", block)
            title = re.search(r"<news:title>([^<]+)</news:title>", block)
            pub = re.search(r"<news:publication_date>(\d{4}-\d{2}-\d{2})", block)
            if not (loc and title and pub):
                continue
            url, date = loc.group(1).split("?")[0], dt.date.fromisoformat(pub.group(1))
            title = html.unescape(title.group(1)).strip()
            if url in have or not (since <= date <= until) or not NEWS_KW.search(title):
                continue
            have.add(url)
            out.append({"source": "WSJ", "title": title, "url": url, "date": date.isoformat(), "abstract": ""})
    except Exception:  # noqa: BLE001  (RSS alone is enough)
        pass
    return out


def fetch_bloomberg(since, until):
    return [c for c in fetch_rss_news("Bloomberg", BLOOMBERG_FEEDS, since, until)
            if "/news/videos/" not in c["url"] and "/news/audio/" not in c["url"]]


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", default=dt.date.today().isoformat())
    ap.add_argument("--out", default="candidates.json")
    ap.add_argument("--only", default="", help="comma list: arxiv_econ,arxiv_qfin,informs,nber,nyt,economist,wapo,wsj,bloomberg,ft")
    a = ap.parse_args()
    since, until = dt.date.fromisoformat(a.since), dt.date.fromisoformat(a.until)

    seen = load_seen()
    seen_urls = {norm_url(e["url"]) for e in seen}
    seen_titles = {norm_title(e.get("title", "")) for e in seen}

    # Paper sources publish with a lag (arXiv announces 1-3 days after submission; Crossref deposits trail
    # online publication), so look back a week and rely on the history to skip anything already sent.
    papers_since = since - dt.timedelta(days=PAPER_LOOKBACK_DAYS)
    jobs = {
        "arxiv_econ": lambda: fetch_arxiv("econ", papers_since, until),
        "arxiv_qfin": lambda: fetch_arxiv("qfin", papers_since, until),
        "informs": lambda: fetch_informs(papers_since, until),
        "nber": lambda: fetch_nber(papers_since, until, seen_urls),
        "nyt": lambda: fetch_nyt(since, until),
        "economist": lambda: fetch_rss_news("Economist", ECONOMIST_FEEDS, since, until),
        "wapo": lambda: fetch_rss_news("Washington Post", WAPO_FEEDS, since, until),
        "wsj": lambda: fetch_wsj(since, until),
        "bloomberg": lambda: fetch_bloomberg(since, until),
        "ft": lambda: fetch_rss_news("Financial Times", FT_FEEDS, since, until),
    }
    only = [s for s in a.only.split(",") if s] or list(jobs)
    status, cands, have = {}, [], set()
    for name in only:
        t0 = time.time()
        try:
            got = jobs[name]()
            kept = 0
            for c in got:
                u = norm_url(c["url"])
                if u in seen_urls or u in have or norm_title(c["title"]) in seen_titles:
                    continue
                have.add(u)
                cands.append(c)
                kept += 1
            status[name] = f"ok: {len(got)} fetched, {kept} new ({time.time() - t0:.0f}s)"
        except Exception as e:  # noqa: BLE001
            status[name] = f"error: {type(e).__name__}: {e} ({time.time() - t0:.0f}s)"
        print(f"{name:12s} {status[name]}", file=sys.stderr, flush=True)

    with open(a.out, "w") as f:
        json.dump({"since": a.since, "until": a.until, "status": status, "candidates": cands}, f,
                  indent=1, ensure_ascii=False)
    print(f"{len(cands)} candidates -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
