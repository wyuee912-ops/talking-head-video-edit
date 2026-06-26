# Talking Head Video Edit

> AI-directed editing pipeline for talking-head videos: transcribe → cut filler → assemble chapters → burn-in stylable subtitles → render. Built for solo creators who want broadcast-grade output without sitting in Premiere all day.

![Pipeline screenshot — input talking-head clip](docs/screenshot.png)

*A frame from a raw talking-head input. The pipeline transcribes it, removes filler/false starts, and renders a final cut with subtitle styling you control via prompt.*

---

## What it does

1. **Transcribes** raw `.mov`/`.mp4` clips using WhisperX (word-level timestamps)
2. **Plans cuts** via an LLM "director" that reads the transcript and decides which segments to keep, trim, or kill
3. **Assembles chapters** with paced edits (J/L cuts, silence trimming, micro-fades)
4. **Burns in subtitles** with full styling control (color, outline, shadow, emoji-safe fonts)
5. **Renders** the final `.mp4` via ffmpeg

The whole thing runs as a CLI pipeline — drop clips in `edit/sources/`, run `scripts/pipeline.py`, get a finished video.

---

## The Director role 🎬

The director is an LLM agent (Claude, GPT, etc.) that reads your transcript and produces an **Editing Decision List (EDL)** — a JSON spec saying "keep 0:03–0:12, kill 0:13–0:18 (false start), keep 0:19–0:45 but trim breath at 0:31, …"

You don't manually scrub the timeline. You give the director a prompt describing the cut you want, and it makes the calls. Examples:

```bash
python scripts/director.py --clip raw_take_1.mov \
  --prompt "Tight 30-second cut for IG Reels. Remove every 'um', false start, and any time I trail off. Keep the punchline at the end intact."
```

The director outputs an EDL the pipeline consumes. You can edit the EDL by hand before rendering if you want surgical control — it's just JSON.

### Common director prompts

| Use case | Prompt |
|---|---|
| **Tight reel** | "Cut to 30s max. Remove fillers, breaths, false starts. Keep the hook in the first 3 seconds." |
| **Tutorial** | "Keep all instructional content. Trim only dead air >0.8s and obvious flubs. Preserve natural pacing." |
| **Podcast clip** | "Extract the strongest 60s standalone moment. Must have a hook + payoff. No mid-thought cuts." |
| **B-roll candidates** | "Mark segments where I look away or pause >1.5s — those are b-roll insertion points." |
| **Bilingual cut** | "Keep both English and Chinese sections. Tag each segment with language for subtitle styling." |
| **Chapter split** | "Identify 3-5 natural chapter breaks. Output an EDL per chapter so I can render them as standalone clips." |

---

## Subtitle styling — the fun part

Subtitles are burned in via ffmpeg's `drawtext`/`subtitles` filters, configured per-segment in the EDL. You can override globally via flags or per-segment in the JSON.

### Text color
```bash
--font-color "#FFFFFF"        # hex
--font-color "yellow"         # named
--font-color "auto"           # pipeline picks high-contrast vs background
```

### Outline (border around text — keeps it readable on busy backgrounds)
```bash
--outline-color "#000000"
--outline-width 3             # px
```

### Shadow (drop shadow for depth)
```bash
--shadow-color "#000000@0.6"  # color + alpha
--shadow-x 2 --shadow-y 2     # offset in px
```

### Combine them
```bash
python scripts/pipeline.py --clip raw_take_1.mov \
  --font "Helvetica Bold" --font-size 56 \
  --font-color "#FFD400" \
  --outline-color "#000" --outline-width 4 \
  --shadow-color "#000@0.7" --shadow-x 3 --shadow-y 3
```

### Per-segment overrides (in the EDL JSON)
```json
{
  "segments": [
    {
      "start": 0.0, "end": 3.2,
      "subtitle_style": {
        "font_color": "#FF4444",
        "outline_color": "#000",
        "outline_width": 5
      }
    },
    {
      "start": 3.2, "end": 8.5,
      "subtitle_style": { "font_color": "auto" }
    }
  ]
}
```

Use this to make the **hook** in your first segment pop with a bright color + heavy outline, then drop back to clean white for the body.

---

## Quick start

```bash
# 1. Install deps
pip install -r requirements.txt
brew install ffmpeg

# 2. Configure
cp .env.example .env
# edit .env — add OPENAI_API_KEY or ANTHROPIC_API_KEY

# 3. Drop a clip in
cp /path/to/your_video.mov edit/sources/

# 4. Run the pipeline
python scripts/pipeline.py --clip your_video.mov \
  --prompt "Tight 30s cut. Remove fillers."

# 5. Output lands in edit/output/
```

---

## Project structure

```
talking-head-edit/
├── scripts/
│   ├── pipeline.py        # main orchestrator
│   ├── director.py        # LLM-powered cut planner
│   ├── batch.py           # batch process multiple clips
│   ├── stitch_chapters.py # combine chapter renders
│   └── paths.py           # path helpers
├── helpers/
│   ├── transcribe.py      # WhisperX wrapper
│   ├── transcribe_batch.py
│   ├── build_pacing_edl.py # EDL builder with pacing rules
│   ├── render.py          # ffmpeg renderer with subtitle styling
│   └── grade.py           # color grade helpers
├── edit/
│   ├── sources/           # drop raw clips here
│   ├── output/            # rendered videos land here
│   └── chapters/          # chapter-by-chapter intermediates
├── fonts/                 # bundled fonts for subtitle rendering
├── DIRECTOR.md            # full director prompt spec
└── SKILL.md               # skill bundle for AI agent usage
```

---

## Configuration

See `.env.example` for required environment variables. At minimum:
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — for the director
- `HF_TOKEN` — optional, for WhisperX speaker diarization

---

## Why this exists

Editing talking-head content is high-volume, low-creativity work for a solo creator. This pipeline turns "60 minutes in Premiere per clip" into "60 seconds of CLI + one prompt." The director catches false starts and "ums" with better accuracy than you'd manually, and subtitle styling is consistent across every video without copy-pasting style settings.

Built with [Cursor](https://cursor.sh) — see commit history for the build journey.

---

## License

MIT
