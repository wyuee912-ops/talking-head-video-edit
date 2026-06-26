# Fonts

libass (ffmpeg subtitles filter) needs the font file on disk.

## Recommended

Copy **Manrope SemiBold** static TTF (not variable font):

```bash
cp /path/to/Manrope-SemiBold.ttf edit/fonts/
```

## Why not ship fonts in this repo

Manrope is licensed separately. Each user/project should add their own font files.

## Troubleshooting

If captions fall back to system font:
- Use static `.ttf`, not variable font
- Ensure `edit/fonts/` is non-empty before render
- EDL must include `"fontsdir": "fonts"`
