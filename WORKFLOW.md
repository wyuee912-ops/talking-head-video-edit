# Workflow recap — how we got here

This documents the real editing session that produced this project, so future runs (human or agent) don't repeat the same mistakes.

---

## 1. Starting point

**Goal:** Edit stage / talking-head speech — not football highlights, not a launch montage.

**User intent:**
- Cut pauses and filler words
- Keep chronological order (don't reorganize into "main points" without context)
- Burn subtitles (Manrope, white on stage)
- Make the pipeline reusable for others

**First source:** `IMG_5223 2.MOV` (~9.5 min SME IPO talk) — pacing cleanup only.

**Batch sources:** 38 clips (`IMG_8240`–`IMG_8364`) from a conference presentation (~9 min total raw).

---

## 2. Editing mode: pacing cleanup vs narrative

| Narrative assembly (video-use default) | Pacing cleanup (this project) |
|----------------------------------------|-------------------------------|
| Pick best takes across clips | Keep every clip in order |
| HOOK → PROBLEM → CTA structure | Same speech, tighter pace |
| Needs domain context | Works without understanding content |
| Multi-take selection | Pause + filler removal |

We chose **pacing cleanup** because the editor lacks full talk context.

---

## 3. Subtitle iteration (what went wrong)

| Attempt | Issue |
|---------|-------|
| 6-word chunks, UPPERCASE Helvetica | Wrong style for speech |
| Black text (`manrope-speech-dark`) | Wrong — white reads better on this footage |
| 6-word cues, 0ms gap between SRT windows | Captions **stacked and jumped** on screen |
| Font 22 → 18 → 16 → **12** | User wanted smaller |
| Heavy outline + shadow | Looked odd — switched to thin outline, shadow=0 |

**Final approved style:**
- `manrope-speech`: Manrope 12, white, outline=1, shadow=0
- 4 words per cue, sequential timing with 100ms gap
- One caption visible at a time

---

## 4. Approval gate (critical)

**Mistake:** Rendered all 38 clips before user reviewed one.

**Fix:** `python scripts/batch.py sample STEM` → snapshot JPG → user approves → `render --force`.

Never skip this for batch work.

---

## 5. Delivery format

**Option considered:** One stitched 8-min video — too heavy to watch.

**Chosen: Option B — 4 chapter videos**

| Chapter | Theme | ~Length |
|---------|-------|---------|
| 01 hook_thesis | Opening, history, GUI agents | 1m 10s |
| 02 product_demos | Use cases, demos | 1m 36s |
| 03 trust_deployment | Guardrails, safety | 2m 14s |
| 04 qa | Audience Q&A | 2m 55s |

Short fragments excluded (8289 "Thank you", 1s false takes, etc.) — still available as individual `*_clean.mp4`.

**Technical note:** Chapters are stitched from source EDLs and subtitles are **re-burned** on the full chapter timeline (don't concat pre-captioned files).

---

## 6. Production rules (non-negotiable)

From video-use, still apply:

1. Subtitles applied **last** in the filter chain
2. Per-segment extract → lossless concat (not single-pass re-encode)
3. 30ms audio fades at every cut boundary
4. Never cut inside a word — snap to transcript boundaries
5. Cache transcripts — don't re-transcribe unchanged sources

---

## 7. Typical session flow

```
Add sources → pipeline plan (director brief)
    → discuss delivery with user → decisions.json
    → sample + snapshot → USER APPROVES captions
    → batch → (optional) stitch chapters
```

**Director agent** handles planning; **editor pipeline** executes only after gates pass.

---

## 8. What to customize per project

- `config/defaults.json` — pause threshold, font size
- `config/chapters.json` — topic groupings
- `edit/fonts/` — your brand font
- Filler word list in `helpers/build_pacing_edl.py`

---

## 9. Subtitle sync (word-timestamp anchoring)

**Problem:** Captions appeared early/late vs speech. Old `_sequence_subtitle_cues` forced 350ms min duration + 100ms gaps, shifting starts and creating overlaps.

**Fix:** Cues anchor to transcript word times:
- **Start** = first word in chunk (never shifted)
- **End** = last word + `tail_pad_s` (default 80ms)
- Overlaps trimmed by shortening previous cue's end only

**Tune in `config/defaults.json` → `caption.offset_s`** if ASR is consistently early/late (try `-0.05` or `+0.05`).

---

## 10. Known limits

- Groq free tier: 20 RPM — batch transcribe may need retry
- Variable fonts may not work with libass — use static `.ttf` (e.g. Manrope-SemiBold)
- Preview renders are 1080p CRF 22 — set `render_preview: false` for final export
- No automatic chapter detection — you define groups in JSON

---

## 11. Social ASS style + title card (approved 2026-07)

For vertical 9:16 social cuts (talks / Q&A reels), the approved look is **ASS burned at 1×**, then **1.2× speed on content only**, with an optional **2.8s title card** prepended at 1.0×.

### Caption style (ASS — not SRT `force_style`)

Burn with `ass=captions.ass:fontsdir=fonts` so font size is real pixels against PlayRes.

| Field | Preview 9:16 | 4K 9:16 |
|-------|--------------|---------|
| PlayRes | **1920×3414** | **2160×3840** |
| Font | Manrope SemiBold | same |
| FontSize | **160** | **180** (~×1.125) |
| Color | white `&H00FFFFFF` | same |
| Outline | **0** | same |
| Shadow | **6** (preview) / **7** (4K) | |
| BackColour | `&H80000000` (50% black) | same |
| Alignment | 2 (bottom-center) | same |
| MarginV | **780** | **878** |
| MarginL/R | **100** | **112** |
| WrapStyle | **2** (single line only) | same |

**Chunking:** ~3 words / cue, ≤~24 chars, ≥100ms gap, never overlap. One cue on screen at a time.

**Order (load-bearing):** burn ASS @ 1.0× → `setpts`/`atempo` 1.2× → prepend title → loudnorm. Do **not** speed before burning captions (timing drifts).

### Title card

- Full-bleed solid black, white Manrope SemiBold, centered both axes
- Size ≈ **2.1% of frame height** (72 on 3414; ~81 on 3840)
- No outline, shadow, box, logo, or chrome
- Hook: 1–2 lines max (question or punchy statement)
- Hold **~2.8s**, hard cut into content
- Title stays at **1.0×**; only the talk content is sped

Example (Qingyi / SafeGround): `SafeGround: know when` / `to trust the click`

### Stage vs social

| | Stage / batch (`manrope-speech`) | Social ASS (this section) |
|--|----------------------------------|---------------------------|
| Engine | SRT + libass `force_style` | Native `.ass` PlayRes |
| Font size | 12 (scaled) | 160 / 180 absolute |
| Outline / shadow | Outline 1, shadow 0 | Outline 0, soft shadow 6–7 |
| Chunking | ~4 words | ~3 words ≤24 chars |
| Speed | 1.0× | Content 1.2× after burn |
| Title card | optional | recommended 2.8s hook |

---

## 12. Transcript → edit loop

For social cuts, the fastest iteration is **edit the transcript, not the timeline**.

### Artifacts

| File | Role |
|------|------|
| `transcripts/<stem>.json` | Word-level ASR (source of truth for times) |
| `full_transcript.md` | Readable source transcript with `[src_start–src_end]` chunks |
| `full_transcript_edited.md` | User (or agent) marks **DELETE** ranges + **FIX** words |
| `kept_transcript.md` | What remains after deletes, mapped to output times |
| `captions_cues.md` | Final ASS cue text for review |
| `edl.json` | Keep windows snapped to word boundaries |

### Rules

1. **DELETE / omit a chunk** → drop that source range from the EDL (still chronological among keeps).
2. **FIX a word** → change caption text only; do **not** retime or re-voice. Audio stays as spoken.
3. Snap every cut to word start/end — never mid-word.
4. After rebuild: regenerate ASS from kept words + fix map → burn @1× → speed content → prepend title → loudnorm.
5. Re-run §13 QC on the new output before handoff.

### Example (SafeGround / Qingyi)

- DELETE intro bio, demo middle (~433–469s src), all Q&A after thank you  
- KEEP hook → method → calibration → results → future work / thank you  
- FIX `GUI-Browing` / `GI-Borne` → `GUI-grounding`, `authenticity` → `uncertainty`, etc.  
- Result: ~339s @1× → ~4:46 with 1.2× + 2.8s title

---

## 13. Quality check (self-eval)

**Do not present a preview until self-eval passes.** Inspect the **rendered output**, not the source files.

### Frame pulls (`verify/`)

```bash
# Bookends
ffmpeg -y -ss 1 -i out.mp4 -frames:v 1 verify/out_1s.jpg
ffmpeg -y -sseof -2 -i out.mp4 -frames:v 1 verify/out_end.jpg

# Every cut boundary (±1.5s) — derive times from EDL output timeline
# Midpoints + known caption risk spots (jargon, typefixes)
ffmpeg -y -ss 65 -i out.mp4 -frames:v 1 verify/qc_caption.jpg
```

Also: `ffprobe` duration vs expected (EDL sum / speed + title duration).

### Pass / fail

| Check | Fail if… |
|-------|----------|
| Orientation | Sideways / mirrored phone rotation |
| Cut audio | Mid-word chop, click, missing fade |
| Cut video | Black flash, jump on action |
| Captions | Overlap, wrong typefix, unreadable, early/late vs speech |
| Title | Wrong copy, held too long/short, sped with content |
| Duration | Off by >0.3s from plan |
| Coherence | Grade/exposure wild between segments |

**Cap at 3** fix → re-render → re-eval loops. If issues remain, list them for the user instead of looping forever.

### Batch gate (still required)

`sample STEM` → snapshot JPG → user approves captions → only then `batch --force`. Never batch-render 30+ clips before one approved sample.
