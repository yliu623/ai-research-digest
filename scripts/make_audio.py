#!/usr/bin/env python3
"""Turn each recent digest's `briefing` script into a two-voice MP3 and attach it to a GitHub Release.

Runs in GitHub Actions (needs GEMINI_API_KEY, GH_TOKEN, ffmpeg and gh on PATH).
Usage: python3 scripts/make_audio.py [--days 3] [--force DATE]

For every digest dated within the last N days that has a briefing and no `audio-<date>` release yet:
  briefing lines -> Gemini TTS (Interactions API, 2 speakers) in chunks -> PCM -> ffmpeg MP3 -> gh release.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
SPEAKERS = {"A": ("Alex", os.environ.get("VOICE_A", "Puck")),
            "B": ("Sam", os.environ.get("VOICE_B", "Kore"))}
CHUNK_WORDS = 320  # keep each request short; turns are never split


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


def release_exists(tag):
    return subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0


def make(date, lines, key):
    pcm, rate = b"", 24000
    for i, ch in enumerate(chunks(lines)):
        data, rate = tts_chunk(ch, key)
        pcm += data + b"\x00\x00" * int(rate * 0.35)  # short pause between chunks
        print(f"  chunk {i + 1}: {len(ch)} turns", flush=True)
    tmp = tempfile.mkdtemp()
    wav_path = os.path.join(tmp, "briefing.wav")
    mp3_path = os.path.join(tmp, f"briefing-{date}.mp3")
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav_path, "-ac", "1", "-b:a", "48k",
                    "-metadata", f"title=AI Research Digest briefing {date}", mp3_path], check=True)
    secs = len(pcm) / 2 / rate
    subprocess.run(["gh", "release", "create", f"audio-{date}", mp3_path,
                    "--title", f"Audio briefing {date}",
                    "--notes", f"Two-voice audio briefing for the {date} AI Research Digest ({secs / 60:.1f} min)."],
                   check=True)
    print(f"  released audio-{date} ({secs / 60:.1f} min, {os.path.getsize(mp3_path) / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--force", default="", help="regenerate this date even if a release exists")
    a = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set; skipping audio")
        return
    cutoff = dt.date.today() - dt.timedelta(days=a.days)
    failures = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "digests", "digest-*.json"))):
        with open(path) as f:
            d = json.load(f)
        date = d["date"]
        lines = [ln for ln in d.get("briefing") or [] if ln.get("speaker") in SPEAKERS and ln.get("text")]
        if not lines or (dt.date.fromisoformat(date) < cutoff and date != a.force):
            continue
        if release_exists(f"audio-{date}"):
            if date != a.force:
                continue
            subprocess.run(["gh", "release", "delete", f"audio-{date}", "--yes", "--cleanup-tag"], check=True)
        print(f"{date}: {len(lines)} turns", flush=True)
        try:
            make(date, lines, key)
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"  FAILED: {e}", file=sys.stderr)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
