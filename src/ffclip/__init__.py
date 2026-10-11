#!/usr/bin/env python3
"""
ffclip — humane ffmpeg. The 10 media recipes everyone googles, with sane
defaults. Thin wrapper, zero dependencies; ffmpeg/ffprobe do the real work.

    ffclip compress  input.mp4 output.mp4      # WhatsApp-friendly H.264
    ffclip audio     input.mp4 output.mp3      # extract audio
    ffclip gif       input.mp4 out.gif --from 10 --to 15
    ffclip trim      input.mp4 out.mp4 --from 90 --to 150
    ffclip mute      input.mp4 out.mp4         # strip audio
    ffclip thumb     input.mp4 shot.jpg --at 5
    ffclip concat    list.txt  out.mp4         # same-codec files
    ffclip resize    input.mp4 out.mp4 --width 1280
    ffclip speed     input.mp4 out.mp4 --factor 2
    ffclip info      input.mp4

Times accept seconds (90, 90.5) or HH:MM:SS.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

VERSION = "0.1.0"


def die(msg, code=1):
    print(f"ffclip: error: {msg}", file=sys.stderr)
    sys.exit(code)


def need(prog):
    if not shutil.which(prog):
        die(f"{prog} not found — install ffmpeg (https://ffmpeg.org/download.html)")
    return prog


def parse_time(s):
    """'90' | '90.5' | '1:30' | '01:02:03' -> seconds (float)."""
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(":")
    if not 2 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        die(f"bad time {s!r}: use seconds or HH:MM:SS")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, sec = parts
    return h * 3600 + m * 60 + sec


def fmt_time(secs):
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def run_ffmpeg(args, quiet=False):
    if not quiet:
        print(f"ffclip: ffmpeg {' '.join(args)}", file=sys.stderr)
    rc = subprocess.run([need("ffmpeg"), "-hide_banner", "-loglevel", "warning" if quiet else "info",
                         "-y"] + args).returncode
    if rc != 0:
        die(f"ffmpeg failed (exit {rc})", rc if 0 < rc < 128 else 1)


def guard_out(path, force):
    if os.path.exists(path) and not force:
        die(f"output exists: {path} (use --force to overwrite)")
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        die(f"output directory does not exist: {parent}")


def check_in(path):
    if not os.path.isfile(path):
        die(f"input not found: {path}")


def probe(path):
    try:
        out = subprocess.run(
            [need("ffprobe"), "-v", "error", "-show_format", "-show_streams",
             "-of", "json", path],
            capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        die(f"ffprobe failed on {path}: {e}")


# ---------------------------------------------------------------- recipes

def r_compress(a):
    check_in(a.input); guard_out(a.output, a.force)
    run_ffmpeg(["-i", a.input,
                "-vf", f"scale={a.width}:-2",
                "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", a.output])


def r_audio(a):
    check_in(a.input); guard_out(a.output, a.force)
    run_ffmpeg(["-i", a.input, "-vn", "-c:a", "libmp3lame", "-b:a", a.bitrate, a.output])


def r_gif(a):
    check_in(a.input); guard_out(a.output, a.force)
    start, end = parse_time(a.frm), parse_time(a.to)
    if end <= start:
        die("--to must be after --from")
    filt = f"fps={a.fps},scale={a.width}:-1:flags=lanczos"
    with tempfile.TemporaryDirectory(prefix="ffclip-") as td:
        pal = os.path.join(td, "palette.png")
        run_ffmpeg(["-ss", fmt_time(start), "-to", fmt_time(end), "-i", a.input,
                    "-vf", filt + ",palettegen", "-y", pal], quiet=True)
        run_ffmpeg(["-ss", fmt_time(start), "-to", fmt_time(end), "-i", a.input,
                    "-i", pal, "-lavfi", filt + " [x]; [x][1:v] paletteuse",
                    "-y", a.output], quiet=True)
    print(f"ffclip: wrote {a.output}", file=sys.stderr)


def r_trim(a):
    check_in(a.input); guard_out(a.output, a.force)
    start, end = parse_time(a.frm), parse_time(a.to)
    if end <= start:
        die("--to must be after --from")
    run_ffmpeg(["-ss", fmt_time(start), "-to", fmt_time(end), "-i", a.input,
                "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                "-c:a", "aac", a.output])


def r_mute(a):
    check_in(a.input); guard_out(a.output, a.force)
    run_ffmpeg(["-i", a.input, "-c", "copy", "-an", a.output])


def r_thumb(a):
    check_in(a.input); guard_out(a.output, a.force)
    run_ffmpeg(["-ss", fmt_time(parse_time(a.at)), "-i", a.input,
                "-frames:v", "1", "-q:v", "2", a.output])


def r_concat(a):
    check_in(a.input); guard_out(a.output, a.force)
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", a.input, "-c", "copy", a.output])


def r_resize(a):
    check_in(a.input); guard_out(a.output, a.force)
    if a.width:
        vf = f"scale={a.width}:-2"
    else:
        vf = f"scale=-2:{a.height}"
    run_ffmpeg(["-i", a.input, "-vf", vf, "-c:v", "libx264", "-crf", "20",
                "-preset", "medium", "-c:a", "copy", a.output])


def atempo_chain(factor):
    """atempo only takes 0.5..2.0 — chain filters for wider ranges."""
    if factor <= 0:
        die("--factor must be > 0")
    stages, f = [], factor
    while f > 2.0:
        stages.append(2.0); f /= 2.0
    while f < 0.5:
        stages.append(0.5); f /= 0.5
    stages.append(round(f, 6))
    return ",".join(f"atempo={s}" for s in stages)


def r_speed(a):
    check_in(a.input); guard_out(a.output, a.force)
    run_ffmpeg(["-i", a.input,
                "-vf", f"setpts=PTS/{a.factor}",
                "-af", atempo_chain(a.factor),
                "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                a.output])


def r_info(a):
    check_in(a.input)
    meta = probe(a.input)
    fmt = meta.get("format", {})
    dur = float(fmt.get("duration", 0) or 0)
    size = int(fmt.get("size", 0) or 0)
    print(f"{a.input}: {fmt_time(dur)}  {size / 1e6:.1f} MB")
    for s in meta.get("streams", []):
        if s["codec_type"] == "video":
            fps = s.get("avg_frame_rate", "?")
            print(f"  video: {s.get('codec_name')} {s.get('width')}x{s.get('height')} @ {fps}fps")
        elif s["codec_type"] == "audio":
            print(f"  audio: {s.get('codec_name')} {s.get('channels')}ch {s.get('sample_rate')}Hz")
        else:
            print(f"  {s['codec_type']}: {s.get('codec_name')}")


# ---------------------------------------------------------------- cli

def add_common(p):
    p.add_argument("input")
    p.add_argument("output")


def build_parser():
    p = argparse.ArgumentParser(prog="ffclip", description="Humane ffmpeg: 10 common media recipes.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--force", "-y", action="store_true", help="overwrite existing outputs")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compress", help="shrink video for sharing (H.264/AAC)")
    add_common(c); c.add_argument("--crf", type=int, default=28); c.add_argument("--width", type=int, default=1280)
    c.set_defaults(func=r_compress)

    au = sub.add_parser("audio", help="extract audio to mp3")
    add_common(au); au.add_argument("--bitrate", default="192k")
    au.set_defaults(func=r_audio)

    g = sub.add_parser("gif", help="GIF from a segment (good palette, not garbage)")
    add_common(g); g.add_argument("--from", dest="frm", required=True); g.add_argument("--to", required=True)
    g.add_argument("--width", type=int, default=480); g.add_argument("--fps", type=int, default=15)
    g.set_defaults(func=r_gif)

    t = sub.add_parser("trim", help="cut a segment, frame-accurate")
    add_common(t); t.add_argument("--from", dest="frm", required=True); t.add_argument("--to", required=True)
    t.set_defaults(func=r_trim)

    m = sub.add_parser("mute", help="strip the audio track")
    add_common(m); m.set_defaults(func=r_mute)

    th = sub.add_parser("thumb", help="grab one frame as an image")
    add_common(th); th.add_argument("--at", default="5")
    th.set_defaults(func=r_thumb)

    cc = sub.add_parser("concat", help="join same-codec files listed in a text file")
    add_common(cc); cc.set_defaults(func=r_concat)

    rs = sub.add_parser("resize", help="scale video, keeping aspect ratio")
    add_common(rs)
    grp = rs.add_mutually_exclusive_group(required=True)
    grp.add_argument("--width", type=int); grp.add_argument("--height", type=int)
    rs.set_defaults(func=r_resize)

    sp = sub.add_parser("speed", help="change playback speed (video + audio)")
    add_common(sp); sp.add_argument("--factor", type=float, required=True)
    sp.set_defaults(func=r_speed)

    ii = sub.add_parser("info", help="human-readable media summary")
    ii.add_argument("input"); ii.set_defaults(func=r_info)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    need("ffmpeg")
    args.func(args)


if __name__ == "__main__":
    main()
