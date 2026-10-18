# screenstudio-export

**Export Screen Studio `.screenstudio` projects to MP4 — free, no app, no subscription.** Reproduces zooms, the animated cursor, webcam bubble, cuts, and backgrounds with Python + ffmpeg.

> Screen Studio stores recordings as proprietary `.screenstudio` bundles that only export through a paid subscription. **screenstudio-export** reads that bundle and renders a finished MP4 with Python and ffmpeg — reproducing zooms, the animated cursor, webcam bubble, cuts, and backgrounds — with no app and no subscription.

*Not affiliated with, endorsed by, or sponsored by Screen Studio. `.screenstudio` is a file format produced by the Screen Studio app; this project reads it for interoperability, on your own recordings, on your own machine. If you value the app's one-click polish and ongoing development, [support the developer](https://screen.studio).*

## The free workflow

1. Download [Screen Studio](https://screen.studio) (free to download — recording, editing, and saving projects all work without a plan; only **export** is subscription-gated).
2. Record your video, add zooms/cuts as usual, and **save the project** (a `.screenstudio` bundle).
3. Point this tool at the bundle → finished MP4.

If all you need is the MP4 out of projects you already recorded, that's the whole subscription — **US $108/year, or ~$20 for a single month** — saved (pricing as of July 2026).

## What is a .screenstudio file?

A `.screenstudio` file is a macOS package (a directory) containing everything Screen Studio captured, unencrypted, on your disk: the raw screen recording (HLS/fMP4 segments), microphone + noise-reduced voice tracks, the webcam recording, full mouse telemetry (positions, clicks, cursor shapes + sprite images), and a `project.json` describing every edit — zoom ranges, cuts, background, webcam bubble, shadows. See [docs/format.md](docs/format.md) for the full layout. Because all of that is plain data, a renderer can reproduce the export outside the app.

## How to export a Screen Studio project without a subscription

```bash
git clone https://github.com/vignesh-sabhahit/screenstudio-export
cd screenstudio-export
brew install ffmpeg && pip3 install pillow     # one-time requirements

./export.sh ~/Recordings/MyDemo.screenstudio
```

That's it. The MP4 lands in `~/Movies/Screen Studio Exports/MyDemo.mp4`, with your cuts, zooms,
speed changes and cursor. Export several projects at once, or pick the output folder:

```bash
./export.sh -o ~/Desktop/videos ~/Recordings/*.screenstudio
./export.sh ~/Recordings/MyDemo.screenstudio -- --frame sunset.jpg   # render options after --
```

`export.sh` checks the requirements, then runs each step for you and cleans up its temp files
(`--keep-work` keeps them, e.g. to debug). The steps, if you want to run them by hand:

```bash
python3 scripts/inspect_bundle.py MyDemo.screenstudio           # what's inside, warnings
python3 scripts/merge_sessions.py --bundle MyDemo.screenstudio --work ./work   # join paused/resumed parts; prints bundle to use
python3 scripts/prepare_render.py --bundle <that bundle> --work ./work
python3 scripts/cursor_layer.py   --bundle <that bundle> --work ./work
zsh work/render_preview.sh    # optional 9-second preview
zsh work/render_full.sh && zsh work/audio_build.sh && zsh work/mux.sh
```

Just want the raw recording with zero effects? One stream-copy, done in seconds:

```bash
ffmpeg -i MyDemo.screenstudio/recording/channel-2-display-0.m3u8 \
       -i MyDemo.screenstudio/recording/channel-3-microphone-0.m4a \
       -map 0:v:0 -map 1:a:0 -c copy raw.mp4
```

## What it reproduces

| Effect | Status |
|---|---|
| Cuts / trims (`slices`) | ✅ exact |
| Speed changes (slice `timeScale`) | ✅ each slice sped up/slowed down; changes are instant, not eased |
| Paused/resumed recordings (multiple sessions) | ✅ parts joined in order |
| Click-following zooms (`zoomRanges`) | ✅ targets from your real click data; smoothstep easing (≈ the app's spring) |
| Animated cursor | ✅ rendered from mouse telemetry + the bundle's own cursor sprites, hotspot-accurate |
| Click ripples | ✅ expanding-ring on every click |
| Webcam bubble | ✅ size / corner / roundness from project config |
| Rounded corners + shadow | ✅ from project config |
| Background | ✅ project gradient/color — or **bring your own frame image** (`--frame photo.jpg`) |
| Audio | ✅ mic or Screen Studio's noise-reduced track, optional cleanup EQ |
| Motion blur, spring-exact easing, captions | ❌ approximated or skipped — [honest gap list](#fidelity-gaps) |

## Use cases

- **Subscription lapsed, old projects stuck** — export the recordings you already made without re-subscribing.
- **Trial user** — you recorded and edited for free; render the result to MP4.
- **One-off video** — don't pay $108/year for a single export.
- **Legacy lifetime-license holder** — the $229 one-time license was discontinued (Sept 2025); keep rendering your library regardless of plan status.
- **Raw footage for a real NLE** — extract untouched screen/webcam recordings for Premiere, Resolve, or Final Cut.
- **Voice-only extraction** — pull just the noise-reduced narration track.
- **Export failed / app crash recovery** — render the bundle even when the app's exporter won't.
- **Batch / headless / CI rendering** — script it; render a folder of projects unattended, no GUI, no app installed.
- **Custom looks** — backgrounds and aspect ratios the app doesn't offer (any image as your frame).
- **Archival** — get the source media out before deleting projects.

## User variables

Pass these to `export.sh` after `--`, or to `prepare_render.py` directly.

| Option | Default | Meaning |
|---|---|---|
| `--frame IMG` | project gradient | your own background/frame image (cover-cropped) |
| `--frame-blur` | 2.0 | background blur σ (0 = crisp, 8 = heavy) |
| `--screen-frac` | 0.78 | recording size within the canvas (smaller = more background) |
| `--out-width` | 1920 | output width; height follows source aspect |
| `--audio` | auto | `enhanced` (noise-reduced) → `mic` fallback; `mic+system` |
| `--audio-cleanup` | loudnorm | `none` / `loudnorm` / `voice` (de-boom EQ for untreated rooms) |
| `--zooms`, `--cursor`, `--webcam` | on/auto | toggle each effect |
| `--crf`, `--preset` | 18, slow | x264 quality |

## Use as a Claude Code skill

This repo doubles as a [Claude Code](https://claude.com/claude-code) skill that runs the whole pipeline conversationally (inspect → preview → render → verify):

```bash
git clone https://github.com/vignesh-sabhahit/screenstudio-export \
  ~/.claude/skills/screenstudio-export
```

Then in Claude Code: *"export ~/Recordings/MyDemo.screenstudio to mp4, use sunset.jpg as the frame"*.

## FAQ

**Can I export a Screen Studio project without paying?**
Yes. This tool renders the `.screenstudio` bundle to MP4 without the app or a subscription. Recording and editing in the app are free; only its export step is paywalled.

**Can I open a .screenstudio file without the app?**
Yes — it's a plain macOS package. `ls` it, read `project.json`, play the `.m3u8` streams with ffmpeg/VLC, or render the whole project with this tool.

**I let my subscription lapse — how do I get my old recordings out?**
This is the exact case this tool was built for. Your bundles still contain everything; render them here.

**Does it reproduce the zoom and the smooth cursor?**
Yes — zoom targets come from your actual recorded clicks, and the cursor is re-rendered from the bundle's mouse telemetry and cursor sprites (hotspot-accurate, with click ripples).

**Does it work without the Screen Studio app installed?**
Yes. Python 3 + Pillow + ffmpeg only. The app is only needed to *record* new material.

**Is this cracking / piracy / watermark removal?**
No. Nothing is patched, no DRM is circumvented, no license check is bypassed. The bundle is unencrypted data on your own disk, produced from your own recordings; this renders it, like any tool reading a documented file format. There is no watermark involved — the app simply gates export.

**Is this affiliated with Screen Studio?**
No. Independent open-source interoperability project.

## Fidelity gaps

Honesty over hype — versus the app's export:

- Zoom easing is smoothstep, an approximation of the app's proprietary damped-spring curve (close; no overshoot).
- Cursor smoothing is lerp + EMA, not the app's spring; the click ripple is a generic expanding ring.
- No motion blur on zoom/pan. No captions (the transcript isn't stored in the bundle). Speed changes switch instantly at slice boundaries.
- macOS system-wallpaper backgrounds aren't shipped inside bundles — substitute any image via `--frame`.

## Requirements

macOS (bundles are produced on macOS; rendering runs anywhere Python + ffmpeg do), Python 3.10+, Pillow, ffmpeg 8+.

## License

MIT. `.screenstudio` format knowledge documented in [docs/format.md](docs/format.md) was derived by inspecting the author's own recordings.
