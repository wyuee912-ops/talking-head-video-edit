# Talking Head Video Edit

AI-assisted editing for **talking-head** and **stage speech** clips — plus a CapCut-style **demo + corner PiP** compositor.

<p align="left"><img src="docs/description.svg" alt="AI-directed editing pipeline for talking-head videos: transcribe, cut filler, assemble chapters, burn-in stylable subtitles, render." /></p>

![Pipeline screenshot — input talking-head clip](docs/screenshot.png)

*Conference talking-head cut with burned-in captions.*

---

## What you can do

| Goal | Tool | Needs API? |
|------|------|------------|
| **A.** Pace-clean a speech / talking-head (cut fillers, captions, chapters) | `scripts/pipeline.py` | Yes — `GROQ_API_KEY` (free) |
| **B.** Overlay a talking head on a screen demo (rounded PiP) | `helpers/compose_pip.py` | No — ffmpeg + Pillow only |

Most people start with **B** if they already have a demo + head clip. Use **A** when you need transcription, pacing cuts, and subtitles.

---

## Install

```bash
git clone https://github.com/wyuee912-ops/talking-head-video-edit.git
cd talking-head-video-edit

# System
brew install ffmpeg          # macOS; or apt install ffmpeg

# Python 3.10+
pip install pillow requests
```

For the pacing pipeline only:

```bash
cp .env.example .env
# edit .env — paste a free key from https://console.groq.com
```

---

## Path B — Demo + talking-head PiP (fastest)

Put a **screen recording / product demo** under a **rounded talking-head** in the bottom-right corner (CapCut-style face crop + rounded mask).

### 1. You need two files

| Input | What it is |
|-------|------------|
| `--demo` | Screen recording or paced product demo |
| `--head` | Talking-head / webcam take (same story, VO comes from here by default) |

### 2. Check the layout with one still (do this first)

```bash
python helpers/compose_pip.py still --preset capcut_0716 \
  --demo /path/to/demo.mov \
  --head /path/to/head.mov \
  --t 5 \
  -o edit/verify/pip_5s.png
```

Open `edit/verify/pip_5s.png`. If the face crop / corner / roundness looks wrong, stop and tweak (see flags below) before a long render.

### 3. Render the full video

```bash
python helpers/compose_pip.py render --preset capcut_0716 \
  --demo /path/to/demo.mov \
  --head /path/to/head.mov \
  --audio head \
  -o edit/output/pip.mp4
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--preset` | `capcut_0716` | Layout reverse-engineered from a CapCut draft (scale ≈ 0.32, bottom-right, rounded) |
| `--audio` | `head` | `head` = VO only · `demo` = demo audio · `both` = mix · `none` |
| `--duration` | min(demo, head) | Cap output length in seconds |
| `--head-offset` / `--demo-offset` | `0` | Start each input later (seconds) |
| `--canvas` | demo size | e.g. `3840x2160` |
| `--crf` | `18` | Quality (lower = larger / better) |

### 4. Inspect geometry (optional)

```bash
python helpers/compose_pip.py geometry --preset capcut_0716 --canvas 3840x2160
```

Preset numbers also live in `config/defaults.json` → `pip`.

**Tip:** If your talking-head take was reordered in CapCut, export that cut as a new `--head` file (or rebuild a timeline first), then run `compose_pip` on top of the demo.

---

## Path A — Pace-clean a talking head

Transcribe → plan cuts → sample captions → batch render → optional chapter stitch.

### Flow

```
plan → discuss → decisions.json → sample → approve captions → batch → [stitch]
```

### Steps

```bash
# 1. Drop raw clips
mkdir -p edit/sources
cp /path/to/your_clips/*.mov edit/sources/

# 2. Transcribe + build a director brief
python scripts/pipeline.py plan
# → read edit/director/brief.md

# 3. Record what you approved (copy the example, then edit)
cp edit/director/decisions.example.json edit/director/decisions.json
# set delivery, exclude_stems, sample.stem, approvals…
python scripts/director.py apply
python scripts/director.py validate

# 4. Sample one clip for caption look
python scripts/pipeline.py sample YOUR_STEM
# approve → set sample.caption_approved + batch.approved in decisions.json

# 5. Render the batch
python scripts/pipeline.py batch

# 6. Optional chapter stitch (if delivery = chapters)
python scripts/pipeline.py stitch
```

Useful status check:

```bash
python scripts/pipeline.py status
```

Full director playbook: [DIRECTOR.md](./DIRECTOR.md) · session notes: [WORKFLOW.md](./WORKFLOW.md)

### Example director intent

| Use case | What to ask for |
|----------|-----------------|
| Tight reel | Cut to ~30s, kill ums / false starts, keep the hook |
| Tutorial | Keep instruction, trim dead air >0.8s only |
| Chapters | Split into 3–4 topic clips (~1–3 min each) |
| Highlights | Strongest ~90s standalone moment |

---

## Captions & social polish

### Stage style (SRT)

Default for longer / conference cuts — Manrope via ffmpeg `force_style`. See `config/defaults.json`.

### Social style (ASS + title card)

For vertical 9:16 reels: burn **native ASS** (Manrope SemiBold, soft shadow) **before** 1.2× speed, optional **2.8s** black title card.

| Title card | Caption burn-in |
|---|---|
| ![Social title card](docs/screenshot-social-title.jpg) | ![Social ASS caption](docs/screenshot-social-caption.jpg) |

Defaults: `config/defaults.json` → `caption_ass_social`, `title_card`. Spec: [WORKFLOW.md §11](WORKFLOW.md#11-social-ass-style--title-card-approved-2026-07).

### Edit the words, not the timeline

Prefer editing a markdown transcript (`DELETE` / typefixes) over scrubbing an NLE — deletions become cut windows; wording fixes become caption text only. Details: [WORKFLOW.md §12](WORKFLOW.md#12-transcript--edit-loop).

### QC before you ship

Pull frames from the **rendered** file into `verify/` — cuts, captions, title, bookends. Checklist: [WORKFLOW.md §13](WORKFLOW.md#13-quality-check-self-eval).

| Cut boundary | Caption spot-check |
|---|---|
| ![QC cut](docs/screenshot-qc-cut.jpg) | ![QC caption](docs/screenshot-qc-caption.jpg) |

---

## Project structure

```
talking-head-video-edit/
├── helpers/
│   ├── compose_pip.py       # Path B — demo + rounded talking-head PiP
│   ├── transcribe.py        # Groq Whisper (word timestamps)
│   ├── build_pacing_edl.py  # pause / filler EDL
│   ├── render.py            # ffmpeg + subtitles
│   └── grade.py
├── scripts/
│   ├── pipeline.py          # Path A — plan / sample / batch / stitch
│   ├── director.py          # inventory, brief, gates
│   ├── batch.py
│   └── stitch_chapters.py
├── config/
│   ├── defaults.json        # captions, title card, pip preset
│   └── chapters.example.json
├── edit/
│   ├── sources/             # drop raw clips here
│   ├── output/              # renders land here
│   ├── verify/              # stills for layout / QC
│   └── director/            # brief + decisions
├── fonts/                   # Manrope for ASS / SRT burn-in
├── DIRECTOR.md
├── WORKFLOW.md
└── SKILL.md                 # Cursor / agent skill bundle
```

---

## Requirements

| | PiP only | Full pacing pipeline |
|--|--|--|
| `ffmpeg` | ✅ | ✅ |
| Python 3.10+ | ✅ | ✅ |
| `pillow` | ✅ | ✅ |
| `requests` | — | ✅ |
| `GROQ_API_KEY` | — | ✅ (free tier) |

---

## Why this exists

Editing talking-head content is high-volume, low-creativity work. This repo turns “an hour in CapCut / Premiere” into a small set of CLI steps — with a director gate so you approve the plan before batch render, and a PiP helper so demo + head layouts stay reproducible.

Built with [Cursor](https://cursor.com).

---

## License

MIT
