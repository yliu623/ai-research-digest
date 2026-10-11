# AI Research Digest

A daily digest of new papers and news about AI / LLMs in economics, finance, and operations / supply chain.

- **Archive site:** https://yliu623.github.io/ai-research-digest/ — every run, searchable, with a daily two-voice
  audio briefing and a 🎧 NotebookLM button on each paper.
- **Daily run:** a Claude Code cloud routine follows [PROMPT.md](PROMPT.md) every morning, emails the digest,
  and pushes `digests/` + `data/` to `main`.
- **Site build:** [.github/workflows/site.yml](.github/workflows/site.yml) turns the briefing into an MP3
  (Gemini TTS, stored as a GitHub Release `audio-<date>`) and deploys the site to GitHub Pages.

| Path | What it is |
|---|---|
| `digests/digest-YYYY-MM-DD.json` | one file per run (the source of truth) |
| `data/seen-items.json` | every URL ever sent — the dedup history and the window start |
| `scripts/fetch_sources.py` | dated candidates from arXiv, Crossref (INFORMS), NBER, NYT, Economist, WaPo |
| `scripts/check_digest.py` | sanity checks before sending |
| `scripts/build_email.py` | plain-text + inline-styled HTML email |
| `scripts/history.py` | window start, dedup set, merge |
| `scripts/build_site.py`, `scripts/make_audio.py`, `site/` | archive site and audio (run in Actions) |

Run locally: `python3 scripts/build_site.py && python3 -m http.server -d _site 8000`.

Secrets: `GEMINI_API_KEY` (repo Actions secret) for the audio briefing. The email recipient lives only in the
routine prompt, not in this repo.
