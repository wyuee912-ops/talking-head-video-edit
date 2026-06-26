# talking-head-edit

Curated pipeline for **speech-based / talking-head** video — tighten pacing, burn subtitles, optionally group into chapter videos. Built for use with AI agents (Cursor, Claude Code) or standalone from the terminal.

**Not** a narrative re-editor. It keeps your speech in order and removes dead air, filler, and awkward pauses — without needing to understand your topic.

---

## Why this exists

Most AI video tools assume you want a **highlight reel** (hook → problem → solution → CTA). That breaks down when:

- You don't have domain context for the speech
- The talk should stay **chronological**
- You have **many short takes** from one session (stage, interview, course)

This project encodes what we learned editing a real 38-clip conference talk:

| Problem we hit | Solution we baked in |
|----------------|---------------------|
| Reorganizing speech without context | **Pacing cleanup mode** — cut pauses/filler only |
| Batch rendered before review | **Sample-first approval gate** |
| Captions stacking / jumping | **Sequential SRT** — one cue at a time, 100ms gap |
| Wrong subtitle color | **White Manrope 12** + thin outline (configurable) |
| One 8-min video too heavy | **Chapter stitching** from `config/chapters.json` |

---

## What it does

1. **Transcribe** — word-level timestamps (Groq Whisper)
2. **Pacing EDL** — auto-detect pauses ≥ 0.25s, remove filler words
3. **Sample render** — one clip for caption/pacing approval
4. **Batch render** — all clips with approved settings
5. **Chapter stitch** — group clips into 2–4 topic videos with fresh subtitles on the full timeline

---

## Quick start

### Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) + ffprobe
- Groq API key ([free tier](https://console.groq.com)) → `GROQ_API_KEY`

```bash
cd talking-head-edit
pip install requests
cp .env.example .env   # add GROQ_API_KEY=...
```

### Add footage

Drop `.mov` / `.mp4` files into `edit/sources/` (symlinks OK).

Add **Manrope SemiBold** to `edit/fonts/` (see `fonts/README.md`).

### Pipeline (director → editor)

```bash
# 1. Plan — transcribe, build EDLs, generate director brief
python scripts/pipeline.py plan
# → read edit/director/brief.md, discuss delivery with user

# 2. Record approvals in edit/director/decisions.json
#    (see edit/director/decisions.example.json)
python scripts/director.py apply

# 3. Sample + caption approval
python scripts/pipeline.py sample IMG_8350
# → user OK → set caption_approved + batch.approved in decisions.json

# 4. Batch all clips
python scripts/pipeline.py batch

# 5. Stitch chapters (if delivery = chapters)
python scripts/pipeline.py stitch
```

See [DIRECTOR.md](./DIRECTOR.md) for the director agent playbook.

### Outputs

```
edit/
├── sources/           # your raw takes
├── transcripts/       # cached word-level JSON
├── edls/              # per-clip cut decisions
├── fonts/             # Manrope for libass
├── verify/            # caption preview JPGs
└── output/
    ├── *_clean.mp4    # one tightened clip each
    ├── *_sample.mp4   # approval sample
    └── chapters/      # stitched topic videos
```

---

## Configuration

**`config/defaults.json`**

| Key | Default | Description |
|-----|---------|-------------|
| `min_pause_s` | `0.25` | Cut pauses ≥ this (seconds) |
| `subtitle_style` | `manrope-speech` | White Manrope, 12px, 4 words/cue |
| `grade` | `none` | Color grade preset (`none` for talking head) |
| `render_preview` | `true` | Faster preview encodes; set `false` for final quality |

**`config/chapters.json`** — define topic groups (see `chapters.example.json`).

---

## Subtitle style (`manrope-speech`)

- Manrope 12 Bold, white text
- Thin black outline, no drop shadow
- ~4 words per cue, sentence case
- One caption on screen at a time (sequential timing)

Tweak in `helpers/render.py` → `SUBTITLE_PRESETS["manrope-speech"]`.

---

## Agent usage (Cursor / Claude Code)

Copy or symlink `SKILL.md` into your agent skills folder. The agent should:

1. Never batch-render before sample approval
2. Use pacing cleanup, not narrative restructuring
3. Generate a caption snapshot for visual review
4. Ask before stitching chapters

See [WORKFLOW.md](./WORKFLOW.md) for the full decision log from our session.

---

## Project layout

```
talking-head-edit/
├── README.md
├── DIRECTOR.md          # director agent playbook
├── WORKFLOW.md          # recap + lessons learned
├── SKILL.md             # agent instructions (director + editor)
├── config/
├── scripts/
│   ├── pipeline.py      # orchestrator with gates
│   ├── director.py      # plan + decisions.json
│   ├── batch.py         # editor: transcribe/render
│   └── stitch_chapters.py
├── helpers/
└── edit/
    └── director/        # brief.md, decisions.json, inventory.json
```

Derived from [video-use](https://github.com/browser-use/video-use) with speech-cleanup defaults and caption fixes.

---

## License

MIT — see [LICENSE](./LICENSE). Font files are not included; bring your own Manrope license.
