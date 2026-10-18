---
name: screenstudio-export
description: >
  Export a .screenstudio (Screen Studio) project bundle to MP4 with ffmpeg only — no
  Screen Studio app, no paid export — reproducing the project's effects: cuts/trims,
  click-following zooms, animated cursor + click ripples, webcam bubble, rounded
  corners + shadow, background (user-supplied "frame" image, or the project's
  gradient/color). Use when the user wants to convert, export, render, or "get an mp4
  out of" a .screenstudio bundle/package/project, or mentions rendering a Screen
  Studio recording without the app.
---

# Screen Studio → MP4 exporter

A `.screenstudio` bundle is a macOS package directory (ls it, never cat). Layout:

```
X.screenstudio/
├── meta.json / project.json / recording-markers.json
└── recording/
    ├── channel-1-system-audio-0.{m3u8,m4a} + *.m4s   (HLS: init .mp4 + fragments)
    ├── channel-2-display-0.m3u8 + *.m4s              (main screen video)
    ├── channel-3-microphone-0.{m3u8,m4a} + *.m4s
    ├── channel-4-webcam-0.m3u8 + *.m4s               (may be absent)
    ├── enhanced/…-enhanced.m4a                        (noise-reduced voice, may be absent)
    ├── cursors/*.png + cursors.json                   (sprites + hotspots, POINT units)
    ├── mousemoves-0.json / mouseclicks-0.json / keystrokes-0.json
    └── metadata.json                                  (recorders, bounds, timing anchor)
```

ffmpeg reads the `.m3u8` playlists directly. Effects live in `project.json` under
`.json.config` (background, camera, cursor, shadow, corner radius) and
`.json.scenes[0]` (`slices` = cuts, `zoomRanges` = zooms).

## User variables

Ask only for what's ambiguous; defaults are sensible. The **frame picture** is the
headline option — an image the user supplies to frame/background their video.

| Variable | Flag (prepare_render.py) | Default | Notes |
|---|---|---|---|
| Bundle path | `--bundle` | required | the `.screenstudio` dir |
| Output mp4 | `--output` | `~/Documents/<name>.mp4` | |
| **Frame picture** | `--frame IMG` | none → project gradient/color | cover-cropped to canvas |
| Frame blur | `--frame-blur` | 2.0 | σ; 0 = crisp; 6–8 = heavy SS-like blur |
| Frame darken | `--frame-darken` | 0.03 | keeps screen readable on bright images |
| Output width | `--out-width` | 1920 | height follows source aspect; use source px width for full-res |
| Screen size | `--screen-frac` | 0.78 | window width as fraction of canvas; more background at lower values |
| Webcam | `--webcam` | auto (project `hideCamera`) | `on`/`off` override; margin `--webcam-margin` 40 |
| Zooms | `--zooms` | on | `--zoom-ease` 0.6 s smoothstep in/out |
| Cursor | `--cursor` | auto (project `hideCursor` + data present) | ripples/scale via cursor_layer.py flags |
| Quality | `--crf` / `--preset` | 18 / slow | |
| Audio track | `--audio` | auto = `enhanced` if present else `mic` | also `mic+system` (checks system isn't silent) |
| Audio cleanup | `--audio-cleanup` | loudnorm | `none` (faithful) / `voice` (de-boom EQ + denoise + loudnorm, good for untreated rooms) |

## Workflow

Work dir: create one under the session scratchpad. All scripts live in `scripts/`
next to this file. Prereqs: ffmpeg 8+, python3 + PIL (`brew install ffmpeg`, `pip install pillow`).

**Fast path:** `./export.sh [-o DIR] <bundle>... [-- prepare_render flags]` runs steps 1–5
below end to end (incl. multi-session merge and speed changes) and writes `DIR/<name>.mp4`.
Use the manual steps when you need to preview, tune, or debug.

1. **Inspect** — `python3 scripts/inspect_bundle.py <bundle>`. Read the WARNINGS
   section aloud to the user (VFR, silent system audio, wallpaper-not-in-bundle,
   multi-session, multi-scene…). Confirm variables (esp. frame picture) if the user
   hasn't specified them.

2. **Raw extraction first (guaranteed win)** — stream-copy before anything fancy:
   ```
   ffmpeg -i recording/channel-2-display-0.m3u8 -i <voice.m4a> \
     -map 0:v:0 -map 1:a:0 -c copy -movflags +faststart raw.mp4
   ```
   h264+aac stream-copies clean; only re-encode if codecs are exotic.

3. **Prepare** — if the bundle has several sessions (paused/resumed recording), first run
   `python3 scripts/merge_sessions.py --bundle … --work …` and use the bundle path it prints.
   Then `python3 scripts/prepare_render.py --bundle … --work … [flags]`.
   Emits assets, filtergraphs, `render_preview.sh` / `render_full.sh` /
   `audio_build.sh` / `mux.sh`, and `plan.json` (geometry, zoom→target table,
   verify points, warnings). Sanity-check the zoom table: targets should be spread
   plausibly, nclicks ≥ 1 for click-follow zooms.

4. **Cursor layer** (if enabled) — `python3 scripts/cursor_layer.py --bundle … --work …`.
   ~36k frames ≈ 10–20 min for a 10-min recording → run in background with a watcher.
   Smoke-test first: `--frames F` where F = a click frame (`round(click_t*fps)`), then
   check the PNG has the sprite at the click coords.

5. **Preview before committing** — `zsh render_preview.sh` (9 s around the first zoom,
   ultrafast). Extract 2–3 frames (`-update 1`!) and LOOK at them: background right?
   corners/shadow? webcam bubble? cursor riding the zoom? Show the user if they asked
   for specific looks (frame image); iterate cheaply here, never on the full render.

6. **Full render** — `zsh render_full.sh` in background (≈0.5–1× realtime; cursor layer
   decode costs ~2×). Renders video-only. Then `zsh audio_build.sh` (slices-cut voice +
   cleanup) and `zsh mux.sh` (stream-copy join → final mp4).

7. **VERIFY (non-negotiable)** — using `plan.json.verify_points` (src_t ↔ out_t pairs):
   extract frames from raw.mp4 at `src_t` and final mp4 at `out_t` — content must
   match at every point (catches the VFR drift bug). If cursor: extract final frame at
   a click time, confirm pointer visible at the right spot. Check duration ≈
   `plan.out_dur_s`. Open the result (QuickTime) for the user.

8. **Report honestly** — list what was reproduced vs approximated vs skipped (below).

## Hard-won gotchas (violate these and the render breaks)

- **VFR sync trap (the big one).** Screen captures are VFR: `r_frame_rate` 60 but
  `avg_frame_rate` ~45. `zoompan` counts frames, ignoring PTS → video runs ahead of
  audio, drifting worse every second, and zooms fire on the wrong content. The chain
  MUST begin `fps=<fps>,setpts=PTS-STARTPTS` before zoompan. Verify with step 7 —
  frames at matched times, early AND late in the video.
- **`crop` cannot animate zoom** — its w/h evaluate once at init. Use `zoompan`
  (per-frame; clock = `on/<fps>`, output frame index; `d=1`).
- **Cursor overlays pre-zoom.** Composite the cursor onto the display stream between
  the fps fix and zoompan → it scales/pans with content automatically. Mouse coords
  are POINTS; scale the layer by pt→px (= display_px / bounds_pt, usually 2.0) at
  overlay time. If `recordingCrop` ≠ full frame, overlay at `-crop_x:-crop_y`.
- **Timing anchor**: event time − `processTimeStartMs` (input recorder's session) =
  seconds into the video. HLS start PTS is huge (e.g. 469601s); `setpts=PTS-STARTPTS`
  zero-bases it.
- **`mouseclicks-0.json` holds mouseDown/mouseUp pairs** — N entries = N/2 clicks.
  Ripples on mouseDown only. Zoom-target centroids may use all entries (harmless).
- **The OS cursor is NOT in the screen capture** — Screen Studio records it as data
  and re-renders. No cursor layer = no cursor at all.
- **ffmpeg 8.x flags**: single-image output needs `-update 1`; filtergraph-from-file
  is `-/filter_complex file.txt` (`-filter_complex_script` is deprecated).
- **Cap looped image inputs** (`-loop 1 -t <dur+5>`) or trim/concat graphs never end.
- **Alpha overlay codec**: qtrle + `-pix_fmt argb` (fallback `png`). prores_4444 works
  but is huge. Never probe a `.mov` mid-write — no moov atom until the encoder exits.
- **System audio may be silent** — volumedetect < −70 dB mean → exclude it.
- **x264 needs even dimensions** everywhere (`even()` all geometry) + `yuv420p`.
- Background `backgroundType: "system"` references a wallpaper that is NOT in the
  bundle → user frame image or project gradient fallback.

## Fidelity gaps to disclose (approximations by design)

- Zoom easing: smoothstep ≈ Screen Studio's proprietary damped spring (close; no overshoot).
- Cursor easing: lerp + EMA ≈ SS's spring smoothing; ripple is a generic expanding ring.
- Motion blur on zoom/pan: skipped. Captions (`showTranscript`): no transcript in bundle.
- Slice `timeScale` ≠ 1: applied per slice (setpts/atempo); speed switches instantly, no easing.
- macOS system wallpaper backgrounds: not in bundle — substituted.
