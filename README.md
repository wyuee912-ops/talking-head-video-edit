# Talking Head Video Edit

CLI toolkit for two kinds of talking-head videos:

| Type | What it looks like | Typical use |
|------|--------------------|-------------|
| **Social reels** | Vertical talking head + captions (+ title card) | IG / TikTok / conference clips |
| **Demo videos** | Screen recording + rounded talking-head PiP | Product walkthroughs, tutorials (16:9) |
| **Demo split** | Demo on top + talking head below | TikTok / IG product demos (9:16) |

---

## Type 1 — Social reels

Pace-clean a stage or webcam take, burn captions, optional title card for 9:16.

![Talking-head reel input](docs/screenshot.png)

*Conference talking-head cut — transcribed, trimmed, captions burned in.*

| Title card | Caption burn-in |
|---|---|
| ![Social title card](docs/screenshot-social-title.jpg) | ![Social ASS caption](docs/screenshot-social-caption.jpg) |

*Left: 2.8s black title card. Right: Manrope SemiBold ASS captions (soft shadow).*

### How to make one

```bash
# 1. Install
brew install ffmpeg
pip install -r requirements.txt
cp .env.example .env   # add free GROQ_API_KEY from https://console.groq.com

# 2. Drop clips
mkdir -p edit/sources
cp /path/to/your_clips/*.mov edit/sources/

# 3. Plan → approve → sample → batch
python scripts/pipeline.py plan
cp edit/director/decisions.example.json edit/director/decisions.json
# edit decisions.json (delivery, sample stem, approvals)
python scripts/director.py apply && python scripts/director.py validate
python scripts/pipeline.py sample YOUR_STEM
python scripts/pipeline.py batch
# optional chapters:
python scripts/pipeline.py stitch
```

Flow: `plan → discuss → decisions.json → sample → approve captions → batch → [stitch]`

More: [DIRECTOR.md](./DIRECTOR.md) · social ASS / title card / QC in [WORKFLOW.md](./WORKFLOW.md)

---

## Type 2 — Demo videos (screen + talking-head PiP)

A **product demo / screen recording** fills the frame. Your **talking head** sits in a rounded rectangle in the bottom-right (CapCut-style face crop). Audio defaults to the talking-head VO.

### What the output looks like

| Product UI | Agent flow | Gmail walkthrough |
|---|---|---|
| ![Demo PiP — product UI](docs/screenshot-demo-pip-5s.jpg) | ![Demo PiP — agent connect](docs/screenshot-demo-pip-18s.jpg) | ![Demo PiP — Gmail walkthrough](docs/screenshot-demo-pip-30s.jpg) |

*Rounded talking-head overlay stays bottom-right while the screen demo leads.*

### How to make one

You need **two inputs**:

| Input | Role |
|-------|------|
| `--demo` | Screen recording / paced product demo |
| `--head` | Webcam / talking-head take (VO source) |

```bash
# 1. Install (no API key)
brew install ffmpeg
pip install -r requirements.txt

# 2. Check layout with one still BEFORE a long render
python helpers/compose_pip.py still --preset capcut_0716 \
  --demo /path/to/demo.mov \
  --head /path/to/head.mov \
  --t 5 \
  -o edit/verify/pip_5s.png

# 3. Render
python helpers/compose_pip.py render --preset capcut_0716 \
  --demo /path/to/demo.mov \
  --head /path/to/head.mov \
  --audio head \
  -o edit/output/pip.mp4
```

Useful flags:

| Flag | Default | Meaning |
|------|---------|---------|
| `--preset` | `capcut_0716` | Face-crop → scale ≈ 0.32 → rounded mask → bottom-right |
| `--audio` | `head` | `head` · `demo` · `both` · `none` |
| `--duration` | auto | Cap length (seconds) |
| `--head-offset` / `--demo-offset` | `0` | Start each clip later |
| `--canvas` | demo size | e.g. `3840x2160` |

```bash
# Inspect resolved pixels
python helpers/compose_pip.py geometry --preset capcut_0716 --canvas 3840x2160
```

Preset numbers: `config/defaults.json` → `pip`.

---

## Type 3 — Demo split (9:16 TikTok / IG)

Same two inputs as Type 2, but stacked for vertical: **demo on top**, **talking head on bottom**, with black pads (CapCut export `0716(1)` layout — not corner PiP).

### What the output looks like

| Mid-demo split | After demo ends |
|---|---|
| ![Vertical split — mid demo](docs/screenshot-demo-split-5s.jpg) | ![Vertical split — head tail](docs/screenshot-demo-split-55s.jpg) |

*While the demo runs: cover-fit demo above head. After the demo ends: top goes black; head stays in the bottom slot.*

### How to make one

```bash
# Still-frame verify
python helpers/compose_split.py still --preset capcut_0716_vertical \
  --demo /path/to/demo.mov \
  --head /path/to/head.mov \
  --t 5 \
  -o edit/verify/split_5s.jpg

# Full render (top blacks out when demo ends; head keeps playing)
python helpers/compose_split.py render --preset capcut_0716_vertical \
  --demo /path/to/demo.mov \
  --head /path/to/head.mov \
  --audio head \
  -o edit/output/vertical.mp4
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--preset` | `capcut_0716_vertical` | 2160×3840 padded split (demo taller than head) |
| `--audio` | `head` | `head` · `demo` · `both` · `none` |
| `--duration` | max(demo, head) | Cap length (seconds) |

```bash
python helpers/compose_split.py geometry --preset capcut_0716_vertical
```

Preset numbers: `config/defaults.json` → `split`.

---

## Install (all types)

```bash
git clone https://github.com/wyuee912-ops/talking-head-video-edit.git
cd talking-head-video-edit
brew install ffmpeg
pip install -r requirements.txt
```

| | Social reels | Demo PiP / split |
|--|:--:|:--:|
| `ffmpeg` | ✅ | ✅ |
| `pillow` + `requests` | ✅ | ✅ (`pillow` only strictly needed) |
| `GROQ_API_KEY` | ✅ free | — |

---

## Project structure

```
talking-head-video-edit/
├── helpers/compose_pip.py   # demo videos — rounded PiP compositor (16:9)
├── helpers/compose_split.py # demo videos — vertical demo/head split (9:16)
├── scripts/pipeline.py      # social reels — plan / sample / batch / stitch
├── scripts/director.py      # inventory, brief, approval gates
├── config/defaults.json     # captions, title card, pip + split presets
├── edit/sources/            # drop raw clips
├── edit/output/             # renders
├── edit/verify/             # stills for layout / QC
├── fonts/                   # Manrope for captions
├── docs/                    # README screenshots
├── DIRECTOR.md
├── WORKFLOW.md
└── SKILL.md
```

---

## QC before you ship

Pull frames from the **rendered** file (not the source):

| Cut boundary | Caption check |
|---|---|
| ![QC cut](docs/screenshot-qc-cut.jpg) | ![QC caption](docs/screenshot-qc-caption.jpg) |

Checklist: [WORKFLOW.md §13](WORKFLOW.md#13-quality-check-self-eval).

---

## License

MIT
