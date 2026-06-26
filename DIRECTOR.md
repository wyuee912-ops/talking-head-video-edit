# Director agent

The **director** plans how footage is delivered. It does not cut video or burn captions — that's the **editor** pipeline (`batch.py`, `stitch_chapters.py`).

This mirrors a real session: the user asks *"how will you stitch this?"* before any export runs.

---

## Roles

| Role | Responsibility |
|------|----------------|
| **Director** | Inventory clips, propose delivery format, chapter groupings, exclusions; get user confirmation |
| **Editor** | Transcribe, pacing EDL, sample render, batch render, stitch (only after director approval) |

---

## Director pipeline

```
sources added
    → transcribe + edl          (editor)
    → director inventory        (scan transcripts)
    → director brief            (markdown plan for user)
    → agent + user conversation (pick delivery, chapters, exclusions)
    → decisions.json            (record approvals)
    → director apply            (sync chapters.json)
    → sample → user OK captions
    → batch → [stitch if chapters]
```

---

## Delivery options (always present to user)

| Option | Output | Best when |
|--------|--------|-----------|
| **individual** | N × `*_clean.mp4` | Social, modular, no stitch |
| **chapters** | 3–4 topic MP4s | Full talk, lighter than one file |
| **full_stitch** | 1 long MP4 | User explicitly wants single file |
| **highlights** | ~90s reel | Promo / trailer |

**Default recommendation for 20+ clips:** start with **individual** or **chapters**, not full_stitch.

---

## What the director brief contains

After `python scripts/director.py brief`, read `edit/director/brief.md`:

1. Clip table — duration, trim %, auto-flags, transcript preview
2. Auto-flags: `fragment`, `false_end`, `qa`, `very_short`
3. Delivery option comparison
4. Empty **Director recommendation** section — **agent fills this**
5. **Questions for user** checklist

The agent must **not** skip to batch/stitch until the user answers.

---

## decisions.json

```json
{
  "version": 1,
  "delivery": "chapters",
  "sample": {
    "stem": "IMG_8350",
    "caption_approved": true
  },
  "batch": { "approved": true },
  "stitch": {
    "approved": true,
    "chapters": [
      {
        "slug": "chapter_01_hook_thesis",
        "title": "Hook + thesis",
        "description": "Opening, history, why GUI agents",
        "clips": ["IMG_8240", "IMG_8252", "..."]
      }
    ]
  },
  "exclude_stems": ["IMG_8289", "IMG_8269"],
  "director_recommendation": "Option B — 4 chapters; drop 1s fragments",
  "user_notes": "User picked chapters over full stitch"
}
```

---

## Gate checks

```bash
python scripts/director.py gate sample   # always OK
python scripts/director.py gate batch    # needs batch.approved + caption_approved
python scripts/director.py gate stitch   # needs stitch.approved + chapters[]
```

`batch.py render` and `stitch_chapters.py` call these unless `--force`.

---

## Agent playbook (how you asked us to plan)

1. **Inventory first** — never assume clip order or narrative from filenames alone
2. **Show the plan in plain English** — table of clips, total runtime, flags
3. **Offer delivery options** — explain tradeoffs (we did: full stitch vs A/B/C/D)
4. **Wait for explicit pick** — user said "Option B", not "stitch everything"
5. **Confirm chapter clip lists** before `stitch_chapters.py`
6. **Sample before batch** — caption style is a director approval, not editor default

---

## Example session (from our work)

1. User sent 38 clip paths → director inventory
2. Agent proposed full stitch (~8 min) → user: *too heavy*
3. Agent offered A/B/C/D → user: **Option B (chapters)**
4. Agent listed exact clip order + flags → user: *tell me before you stitch*
5. Sample `IMG_8350` → caption iterations → user OK → batch 38
6. Stitch 4 chapters from approved groupings

---

## Commands

```bash
python scripts/director.py init
python scripts/director.py inventory
python scripts/director.py brief          # read edit/director/brief.md
# … discuss with user, edit decisions.json …
python scripts/director.py apply
python scripts/director.py validate
```

See [SKILL.md](./SKILL.md) for agent hard rules.
