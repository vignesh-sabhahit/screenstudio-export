#!/usr/bin/env python3
"""
merge_sessions.py — flatten a multi-session .screenstudio bundle into one session.

A recording that was paused/resumed is stored as several sessions per channel
(channel-1-display-0.m3u8, -1.m3u8, ...). Screen Studio's edit timeline (slices,
zooms) runs over those sessions played back to back. The render scripts only
read session 0, so this writes a shadow bundle into --work where every channel
has exactly one session:

  * media of each session is concatenated (stream copy, no re-encode)
  * mouse moves/clicks are shifted onto the joined timeline
  * project.json and everything else are symlinked from the original bundle

Prints the bundle path to render: the original if it has a single session,
otherwise <work>/merged.screenstudio.
"""
import argparse, json, os, subprocess, sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()

    bundle = os.path.abspath(a.bundle.rstrip("/"))
    rec = os.path.join(bundle, "recording")
    meta = json.load(open(os.path.join(rec, "metadata.json")))
    recs = meta["recorders"]
    if all(len(r.get("sessions") or []) <= 1 for r in recs):
        print(bundle)
        return

    disp = next(r for r in recs if r.get("type") == "display")
    # timeline offset of each session = summed durations of the sessions before it
    offs, acc = [], 0.0
    for s in disp["sessions"]:
        offs.append(acc)
        acc += s["durationMs"]
    total_ms = acc

    out = os.path.join(os.path.abspath(a.work), "merged.screenstudio")
    orec = os.path.join(out, "recording")
    os.makedirs(orec, exist_ok=True)
    for name in os.listdir(bundle):
        if name != "recording" and not os.path.lexists(os.path.join(out, name)):
            os.symlink(os.path.join(bundle, name), os.path.join(out, name))
    for name in os.listdir(rec):
        if not os.path.lexists(os.path.join(orec, name)):
            os.symlink(os.path.join(rec, name), os.path.join(orec, name))

    def shift(sessions, key):
        """Concatenate per-session event files, re-timed onto session 0's clock."""
        t0 = sessions[0]["processTimeStartMs"]
        merged = []
        for k, s in enumerate(sessions):
            fn = s.get(key)
            if not fn or not os.path.exists(os.path.join(rec, fn)):
                continue
            d = offs[k] + t0 - s["processTimeStartMs"]
            for e in json.load(open(os.path.join(rec, fn))):
                if "processTimeMs" in e:
                    e["processTimeMs"] += d
                merged.append(e)
        return merged

    for r in recs:
        ss = r.get("sessions") or []
        if len(ss) <= 1:
            continue
        if len(ss) != len(offs):
            sys.exit(f"{r['id']}: {len(ss)} sessions but display has {len(offs)}; cannot align")
        one = dict(ss[0], durationMs=total_ms,
                   processTimeEndMs=ss[0]["processTimeStartMs"] + total_ms)
        if r.get("type") == "input":
            for key in ("mouseMovesFilename", "mouseClicksFilename", "keyStrokesFilename"):
                if ss[0].get(key):
                    fn = f"merged-{r['id']}-{key.replace('Filename', '').lower()}.json"
                    json.dump(shift(ss, key), open(os.path.join(orec, fn), "w"))
                    one[key] = fn
        if ss[0].get("outputFilename"):
            ext = ".m4a" if ss[0]["outputFilename"].endswith(".m4a") else ".mp4"
            fn = f"merged-{r['id']}{ext}"
            lst = os.path.join(a.work, f"concat-{r['id']}.txt")
            with open(lst, "w") as f:
                for s in ss:
                    f.write("file '" + os.path.join(rec, s["outputFilename"]).replace("'", r"'\''") + "'\n")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "concat", "-safe", "0", "-i", lst,
                            "-c", "copy", os.path.join(orec, fn)], check=True)
            one["outputFilename"] = fn
        r["sessions"] = [one]

    os.remove(os.path.join(orec, "metadata.json"))
    json.dump(meta, open(os.path.join(orec, "metadata.json"), "w"), indent=2)
    # prepare_render reads mouseclicks-0.json by fixed name; point it at the merged data
    inp = next((r for r in recs if r.get("type") == "input"), None)
    for src, dst in (("mouseMovesFilename", "mousemoves-0.json"),
                     ("mouseClicksFilename", "mouseclicks-0.json")):
        if inp and inp["sessions"][0].get(src):
            p = os.path.join(orec, dst)
            if os.path.lexists(p):
                os.remove(p)
            os.symlink(inp["sessions"][0][src], p)
    print(out)


if __name__ == "__main__":
    main()
