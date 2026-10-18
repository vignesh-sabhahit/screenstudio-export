#!/usr/bin/env bash
# export.sh — render .screenstudio projects to MP4 in one command.
#
#   ./export.sh [-o OUTPUT_DIR] [--keep-work] PROJECT.screenstudio [MORE ...] [-- RENDER_OPTIONS]
#
# Runs every step of the pipeline (merge sessions -> prepare -> cursor -> render ->
# audio -> mux) for each project, keeping its cuts, zooms and speed changes.
# Each project becomes OUTPUT_DIR/<name>.mp4 (default: ~/Movies/Screen Studio Exports).
# Options after -- go to scripts/prepare_render.py, e.g. -- --frame bg.jpg --crf 20
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$HOME/Movies/Screen Studio Exports"
KEEP_WORK=0
BUNDLES=()
EXTRA=()

usage() {
  sed -n '3,9p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    -o|--output) [ $# -ge 2 ] || usage 1; OUT_DIR="$2"; shift 2 ;;
    --keep-work) KEEP_WORK=1; shift ;;
    -h|--help) usage 0 ;;
    --) shift; EXTRA=("$@"); break ;;
    -*) echo "unknown option: $1" >&2; usage 1 ;;
    *) BUNDLES+=("$1"); shift ;;
  esac
done
[ ${#BUNDLES[@]} -gt 0 ] || usage 1

# ---- requirements ----
missing=0
command -v ffmpeg >/dev/null || { echo "ffmpeg not found. Install it: brew install ffmpeg" >&2; missing=1; }
command -v python3 >/dev/null || { echo "python3 not found. Install it: brew install python" >&2; missing=1; }
if [ $missing -eq 0 ] && ! python3 -c "import PIL" 2>/dev/null; then
  echo "Pillow not found. Install it: pip3 install pillow" >&2; missing=1
fi
[ $missing -eq 0 ] || exit 1

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
failed=()

for b in "${BUNDLES[@]}"; do
  b="${b%/}"
  name="$(basename "$b")"; name="${name%.screenstudio}"
  if [ ! -f "$b/project.json" ] || [ ! -f "$b/recording/metadata.json" ]; then
    echo "!! $b is not a Screen Studio project; skipping" >&2
    failed+=("$name"); continue
  fi
  b="$(cd "$b" && pwd)"
  out="$OUT_DIR/$name.mp4"
  work="$(mktemp -d "${TMPDIR:-/tmp}/screenstudio-export.XXXXXX")"
  log="$work/export.log"

  step() {  # step <label> <command...>; output goes to the log
    echo "   $1"
    shift
    "$@" >>"$log" 2>&1
  }

  echo "== $name"
  # merge_sessions prints the bundle to render: the original, or a merged copy in $work
  if src="$(python3 "$HERE/scripts/merge_sessions.py" --bundle "$b" --work "$work" 2>>"$log")" \
     && step "preparing..." python3 "$HERE/scripts/prepare_render.py" --bundle "$src" --work "$work" --output "$out" ${EXTRA[@]+"${EXTRA[@]}"} \
     && { ! grep -q '"cursor": true' "$work/plan.json" \
          || step "drawing cursor..." python3 "$HERE/scripts/cursor_layer.py" --bundle "$src" --work "$work"; } \
     && step "rendering video (the slow part)..." zsh "$work/render_full.sh" \
     && step "processing audio..." zsh "$work/audio_build.sh" \
     && step "writing mp4..." zsh "$work/mux.sh"; then
    echo "   done -> $out"
    if [ $KEEP_WORK -eq 1 ]; then echo "   work files kept in $work"; else rm -rf "$work"; fi
  else
    echo "!! $name failed. Log: $log" >&2
    failed+=("$name")
  fi
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "Failed: ${failed[*]}" >&2
  exit 1
fi
echo "All done. Videos are in: $OUT_DIR"
