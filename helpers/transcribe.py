"""Transcribe a video with Groq Whisper (whisper-large-v3).

Extracts mono 16kHz mp3 audio via ffmpeg, uploads to Groq with word-level
timestamps, normalises the response to the same {text, start, end, type}
word schema that pack_transcripts.py expects, and writes the result to
<edit_dir>/transcripts/<video_stem>.json.

Cached: if the output file already exists, the upload is skipped.

Requires GROQ_API_KEY in ~/Developer/video-use/.env or the environment.
Free tier available at https://console.groq.com — no credit card needed.

Note: Groq enforces a 25 MB upload limit. At 32 kbps mono mp3 that covers
~100 minutes per clip; split longer takes before transcribing.

Usage:
    python helpers/transcribe.py <video_path>
    python helpers/transcribe.py <video_path> --edit-dir /custom/edit
    python helpers/transcribe.py <video_path> --language en
    python helpers/transcribe.py <video_path> --num-speakers 2
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"
GROQ_UPLOAD_LIMIT_MB = 25


def load_api_key() -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "GROQ_API_KEY":
                    return v.strip().strip('"').strip("'")
    v = os.environ.get("GROQ_API_KEY", "")
    if not v:
        sys.exit("GROQ_API_KEY not found in .env or environment. Get a free key at https://console.groq.com")
    return v


def extract_audio(video_path: Path, dest: Path) -> None:
    # 32 kbps mono mp3 keeps files well under Groq's 25 MB limit (~100 min/clip)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _normalize_words(groq_words: list[dict]) -> list[dict]:
    """Convert Groq word entries {word, start, end} to the pack_transcripts schema."""
    out = []
    for w in groq_words:
        out.append({
            "type": "word",
            "text": w.get("word", ""),
            "start": w.get("start", 0.0),
            "end": w.get("end", w.get("start", 0.0)),
        })
    return out


def call_groq(
    audio_path: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,  # Groq Whisper has no diarization; param kept for API compat
) -> dict:
    size_mb = audio_path.stat().st_size / (1024 * 1024)
    if size_mb > GROQ_UPLOAD_LIMIT_MB:
        sys.exit(
            f"Audio file is {size_mb:.1f} MB, over Groq's {GROQ_UPLOAD_LIMIT_MB} MB limit. "
            "Split the clip into shorter segments and transcribe each one separately."
        )

    data: dict[str, str] = {
        "model": GROQ_MODEL,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
    }
    if language:
        data["language"] = language

    with open(audio_path, "rb") as f:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, f, "audio/mpeg")},
            data=data,
            timeout=1800,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Groq returned {resp.status_code}: {resp.text[:500]}")

    raw = resp.json()
    # Normalise to the pack_transcripts word schema
    return {
        "text": raw.get("text", ""),
        "language": raw.get("language"),
        "duration": raw.get("duration"),
        "words": _normalize_words(raw.get("words") or []),
    }


def transcribe_one(
    video: Path,
    edit_dir: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
    verbose: bool = True,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists.
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    if verbose:
        print(f"  extracting audio from {video.name}", flush=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.wav"
        extract_audio(video, audio)
        size_mb = audio.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"  uploading {video.stem}.wav ({size_mb:.1f} MB)", flush=True)
        payload = call_groq(audio, api_key, language, num_speakers)

    out_path.write_text(json.dumps(payload, indent=2))
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s")
        if isinstance(payload, dict) and "words" in payload:
            print(f"    words: {len(payload['words'])}")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video with Groq Whisper")
    ap.add_argument("video", type=Path, help="Path to video file")
    ap.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit output directory (default: <video_parent>/edit)",
    )
    ap.add_argument(
        "--language",
        type=str,
        default=None,
        help="Optional ISO language code (e.g., 'en'). Omit to auto-detect.",
    )
    ap.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Optional number of speakers when known. Improves diarization accuracy.",
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    api_key = load_api_key()

    transcribe_one(
        video=video,
        edit_dir=edit_dir,
        api_key=api_key,
        language=args.language,
        num_speakers=args.num_speakers,
    )


if __name__ == "__main__":
    main()
