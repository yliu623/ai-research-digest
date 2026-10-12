# Daily AI Research Digest — run instructions

You are the daily run of the AI Research Digest: new papers and news about AI / LLMs applied to
**economics, finance, and operations / supply chain**. Work from the repo root. Follow every step; never
block the email on a non-essential failure (note it in the footnote instead). The routine prompt gives you
the email recipient.

**This run is unattended — nobody will resume you.** Never end your turn to wait for a background task,
monitor or notification; if you do, the run stops and no email goes out. Run long commands in the
foreground with a long Bash timeout (`timeout: 600000`), and keep working until the email is sent and the
push is done (step 8).

## 0. Setup and guard
```bash
TODAY=$(TZ=America/Chicago date +%F)
START=$(python3 scripts/history.py window)      # most recent date_sent in data/seen-items.json
python3 scripts/history.py dedup /tmp/dedup.json
```
If `digests/digest-$TODAY.json` already exists **and has at least one item**, a run already happened today: stop
and report that (do not email again). If it exists with zero items (e.g. sources were blocked), redo the run
and overwrite it.

If `fetch_sources.py` reports `error:` for most sources (e.g. `Tunnel connection failed: 403`), the
environment's network allowlist is missing hosts: say so prominently at the top of the footnote and in your
final report, listing the blocked hosts.

## 1. Collect dated candidates (scripts)
```bash
# foreground, Bash timeout 600000 ms — usually under a minute
python3 scripts/fetch_sources.py --since "$START" --until "$TODAY" --out /tmp/candidates.json
```
This covers arXiv (econ.GN/EM/TH + q-fin.*, exact v1 submission dates), INFORMS Management Science / M&SOM /
Operations Research (Crossref "published-online" dates), NBER (issue date from the paper page), NYT (daily
sitemaps), The Economist (RSS), the Washington Post (RSS), the Wall Street Journal (RSS + news sitemap),
Bloomberg (RSS) and the Financial Times (RSS). News article pages are paywalled/blocked for scripts, so
write news summaries from the feed teaser plus a WebSearch on the headline; never invent details. Every candidate already has a verified in-window
date, matched the keyword list, and is not in history. Paper sources look back 7 days before `$START`
(arXiv and Crossref publish with a lag), so a paper's submission/online date can predate the window —
that's expected; it has never been sent. News must be dated inside the window. Read the per-source status lines; any `error:` goes in
the footnote as one line ("<source> could not be reached this run").

## 2. Sources the scripts can't cover
- **SSRN** — run ~8 WebSearch queries with `allowed_domains: ["papers.ssrn.com","ssrn.com"]`, combining AI
  terms ("large language models", "LLM", "generative AI", "agentic AI", "AI agents", "artificial intelligence",
  "machine learning", "foundation model") with fields (finance, asset pricing, banking, economics, labor
  market, productivity, supply chain, operations). For every candidate, verify the posting date — never use
  the snippet date: (a) WebFetch the abstract page and read "Posted:"; (b) if blocked, `curl -s -A
  "ai-research-digest/1.0" https://api.crossref.org/works/10.2139/ssrn.<id>` and use `posted`, else
  `created` date-parts. No verified in-window date → exclude. Normalize URLs to
  `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=<id>` and skip any in /tmp/dedup.json.
- **Washington Post backfill** — RSS covers only ~2 days. If the window is longer than 2 days, run a few
  WebSearch queries with `allowed_domains: ["washingtonpost.com"]` and keep only URLs whose `/YYYY/MM/DD/`
  date is in the window.

## 3. Judge relevance (apply judgment after keyword matching)
Keep only items genuinely ABOUT AI applied to economics, finance, or operations:
- AI is the subject (economics of AI, adoption, labor/productivity/inequality effects, AI firms, markets and
  investment, LLM agents as economic actors or simulated respondents, AI in banking/trading, AI and supply
  chains, chips/data-center economics), or
- ML / LLMs / deep learning / RL / foundation models are the central method of the contribution.

Drop: "agent" meaning economic agents / principal-agent / agent-based models without AI; econometrics or
optimization papers that mention ML in passing; news about AI culture, arts, health or politics without an
economic angle; podcasts, newsletters, quizzes; duplicate stories (keep the best one); near-duplicates of an
already-sent item (e.g. an SSRN preprint of an already-sent journal article).

## 4. Write the digest JSON — `digests/digest-$TODAY.json`
```json
{"date": "YYYY-MM-DD",
 "sections": [
  {"name": "📊 Economics (NBER / SSRN / arXiv)", "items": [...]},
  {"name": "💵 Finance (SSRN / NBER / arXiv q-fin)", "items": [...]},
  {"name": "📦 Operations & Supply Chain (INFORMS: Management Science, M&SOM, Operations Research)", "items": [...]},
  {"name": "📰 News (NYT / WSJ / Bloomberg / FT / Washington Post / Economist)", "items": [...]}
 ],
 "briefing": [{"speaker": "A", "text": "..."}, {"speaker": "B", "text": "..."}],
 "footnote": "Window: <START> (last run) → <TODAY>. ..."}
```
Section names must match exactly (copy them). Placement: arXiv econ.* → Economics (Finance if mainly about
financial markets; Ops if mainly operations); arXiv q-fin.* → Finance (Economics if mainly macro/labor);
INFORMS → Ops; NBER and SSRN → by topic; news → News. Within a section, newest first.

Each item: `{"title", "url", "fulltext", "date", "desc"}`
- `url` — the abstract/article page (arXiv: `https://arxiv.org/abs/<id>`). Every item must have one.
- `fulltext` — best full-text link (arXiv `https://arxiv.org/pdf/<id>`, NBER PDF); otherwise same as url.
- `desc` — 1–2 plain-text sentences in your own words: what it does and the main finding (concrete; data,
  method, headline number if given; no hype; never invent facts). End with the verified date tag, exactly one of:
  `[arXiv <primary cat>, submitted YYYY-MM-DD]`, `[NBER w<num>, issued YYYY-MM-DD]`,
  `[SSRN, posted YYYY-MM-DD]`, `[Management Science | M&SOM | Operations Research, published online YYYY-MM-DD]`,
  `[NYT | WSJ | Bloomberg | Financial Times | The Economist | Washington Post, published YYYY-MM-DD]`.

**briefing** (omit if there are no items): a two-host audio script, hosts **Alex** (speaker "A") and **Sam**
(speaker "B"), 600–900 words total (~5–6 minutes), 12–24 turns. Open with the date and a one-line overview,
cover the 6–10 most interesting items across sections (say the source, e.g. "a new NBER paper"), explain why
each matters in plain language, keep facts strictly to the summaries, and close with a short sign-off pointing
listeners to the web archive. Spoken style: no URLs, no bracketed tags, no markdown, spell out symbols.

Empty sections are fine — never pad with older material.

## 5. Check
```bash
python3 scripts/check_digest.py "digests/digest-$TODAY.json" --since "$START"
```
Fix every failure before sending.

## 6. Email (the deliverable)
```bash
python3 scripts/build_email.py "digests/digest-$TODAY.json" /tmp/out
```
Read `/tmp/out/email-$TODAY.txt` and `/tmp/out/email-$TODAY.html`, then send with the AgentMail connector's
`send_message`:
- `inboxId`: the `inbox` value in `config.json`
- `to`: [recipient from the routine prompt]
- `subject`: `🗞️ Daily AI Research Digest — <TODAY>`
- `text` / `html`: the two files' contents, verbatim. No attachments.

If it returns an organization error, call `list_organizations`, then `select_organization` for
"Ye's Organization", and retry. If nothing qualified, still send a short email saying "Nothing new in this
window" (with the footnote).

## 7. History + publish
```bash
# only if the digest has at least one item (otherwise the next window widens automatically)
python3 scripts/history.py merge "digests/digest-$TODAY.json"
git add digests data
git commit -m "Digest $TODAY: <N> items"
git push origin HEAD:main || (git pull --rebase origin main && git push origin HEAD:main)
```
Pushing to `main` triggers the GitHub Pages build (archive site + audio briefing).

## 8. Report
Final message: window used, counts per section (e.g. "Economics: 2, Finance: 1, Ops: 0, News: 3"), the
email message id, and any sources that failed.
