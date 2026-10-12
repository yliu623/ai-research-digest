#!/usr/bin/env python3
"""Turn recent digests' audio scripts into two-voice MP3s attached to a GitHub Release per day.

Runs in GitHub Actions (needs GEMINI_API_KEY, GH_TOKEN, ffmpeg and gh on PATH).
Usage: python3 scripts/make_audio.py [--days 3] [--force DATE]

Release `audio-<date>` holds `briefing-<date>.mp3` (the daily briefing) and `p-<id>.mp3` per paper that has a
`podcast` script (id = history.audio_id(url)). Only missing files are made; a Gemini quota error stops the run
cleanly and the next run (push or the daily schedule) continues.
"""
import argparse
import base64
import datetime as dt
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from history import audio_id  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
SPEAKERS = {"A": ("Alex", os.environ.get("VOICE_A", "Puck")),
            "B": ("Sam", os.environ.get("VOICE_B", "Kore"))}
CHUNK_WORDS = 450  # paper explainers fit in one request; turns are never split


def find_audio(obj):
    """Return the last base64 audio payload in an Interactions API response."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "audio" and isinstance(o.get("data"), str):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    if not found:
        raise RuntimeError("no audio in response: " + json.dumps(obj)[:400])
    return found[-1]


def tts_chunk(lines, key):
    body = {
        "model": MODEL,
        "input": [{"type": "user_input", "content": [
            {"type": "text", "text": ln["text"],
             "annotations": [{"type": "speech_metadata", "speaker": SPEAKERS[ln["speaker"]][0],
                              "style": "warm, curious podcast host, natural pace"}]}
            for ln in lines]}],
        "response_format": {"type": "audio", "mime_type": "audio/wav"},
        "generation_config": {"speech_config": {
            "mode": "conversational",
            "speakers": [{"speaker": n, "voice": v} for n, v in SPEAKERS.values()]}},
    }
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 503) and attempt < 3:
                time.sleep(20 * (attempt + 1))
                continue
            raise RuntimeError(f"TTS HTTP {e.code}: {msg}") from None
    audio = find_audio(resp)
    raw = base64.b64decode(audio["data"])
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw)) as w:
            return w.readframes(w.getnframes()), w.getframerate()
    return raw, int(audio.get("sample_rate") or 24000)  # headerless 16-bit mono PCM


def chunks(lines):
    cur, n = [], 0
    for ln in lines:
        w = len(ln["text"].split())
        if cur and n + w > CHUNK_WORDS:
            yield cur
            cur, n = [], 0
        cur.append(ln)
        n += w
    if cur:
        yield cur


def release_assets(tag):
    """Asset names of the day's release, or None if it doesn't exist yet."""
    r = subprocess.run(["gh", "release", "view", tag, "--json", "assets", "-q", ".assets[].name"],
                       capture_output=True, text=True)
    return set(r.stdout.split()) if r.returncode == 0 else None


class QuotaExhausted(Exception):
    pass


def synth(lines, key, out_path, title):
    pcm, rate = b"", 24000
    for ch in chunks(lines):
        try:
            data, rate = tts_chunk(ch, key)
        except RuntimeError as e:
            if "HTTP 429" in str(e):
                raise QuotaExhausted(str(e)) from None
            raise
        pcm += data + b"\x00\x00" * int(rate * 0.35)  # short pause between chunks
    wav_path = out_path[:-4] + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav_path, "-ac", "1", "-b:a", "40k",
                    "-metadata", f"title={title}", out_path], check=True)
    os.remove(wav_path)
    return len(pcm) / 2 / rate


def jobs_for(d):
    """(asset name, script lines, title) for the briefing and every paper explainer in a digest."""
    out = []
    lines = [ln for ln in d.get("briefing") or [] if ln.get("speaker") in SPEAKERS and ln.get("text")]
    if lines:
        out.append((f"briefing-{d['date']}.mp3", lines, f"AI Research Digest briefing {d['date']}"))
    for s in d["sections"]:
        for it in s["items"]:
            pod = [ln for ln in it.get("podcast") or [] if ln.get("speaker") in SPEAKERS and ln.get("text")]
            if pod:
                out.append((f"p-{audio_id(it['url'])}.mp3", pod, it["title"][:120]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--force", default="", help="regenerate all audio for this date")
    ap.add_argument("--max", type=int, default=40, help="max files to generate this run")
    a = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set; skipping audio")
        return
    cutoff = dt.date.today() - dt.timedelta(days=a.days)
    made = failures = 0
    tmp = tempfile.mkdtemp()
    for path in sorted(glob.glob(os.path.join(ROOT, "digests", "digest-*.json")), reverse=True):
        with open(path) as f:
            d = json.load(f)
        date, tag = d["date"], f"audio-{d['date']}"
        if dt.date.fromisoformat(date) < cutoff and date != a.force:
            continue
        have = release_assets(tag)
        if date == a.force and have is not None:
            subprocess.run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], check=True)
            have = None
        todo = [j for j in jobs_for(d) if have is None or j[0] not in have]
        if todo:
            print(f"{date}: {len(todo)} audio file(s) to make", flush=True)
        for name, lines, title in todo:
            if made >= a.max:
                print(f"reached --max {a.max}; the rest will be made on the next run")
                return
            out = os.path.join(tmp, name)
            try:
                secs = synth(lines, key, out, title)
            except QuotaExhausted as e:
                print(f"Gemini quota reached ({e}); the rest will be made on the next run")
                return
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAILED {name}: {e}", file=sys.stderr)
                continue
            if have is None:
                subprocess.run(["gh", "release", "create", tag, out, "--title", f"Audio {date}",
                                "--notes", f"Audio for the {date} AI Research Digest: the daily briefing and "
                                           f"short explainers for individual papers."], check=True)
                have = set()
            else:
                subprocess.run(["gh", "release", "upload", tag, out, "--clobber"], check=True)
            have.add(name)
            made += 1
            print(f"  {name}: {secs / 60:.1f} min, {os.path.getsize(out) / 1e6:.1f} MB", flush=True)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
