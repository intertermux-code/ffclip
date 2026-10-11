"""ffclip tests. Needs ffmpeg/ffprobe on PATH. Run: python -m pytest tests/ -x -q"""
import json
import os
import subprocess
import sys

import pytest

BIN = [sys.executable, "-m", "ffclip"]
HAVE_FFMPEG = bool(__import__("shutil").which("ffmpeg"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


def run(*args, **kwargs):
    return subprocess.run(BIN + list(args), capture_output=True, text=True,
                          timeout=kwargs.pop("timeout", 120), **kwargs)


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
        capture_output=True, text=True, check=True, timeout=30).stdout
    return json.loads(out)


def duration(path):
    return float(ffprobe(path)["format"]["duration"])


def streams_of(path, ctype):
    return [s for s in ffprobe(path)["streams"] if s["codec_type"] == ctype]


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    """2s 320x240 30fps test video with audio."""
    d = tmp_path_factory.mktemp("media")
    v = str(d / "src.mp4")
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", v],
        timeout=60)
    assert r.returncode == 0 and os.path.exists(v)
    return v


@needs_ffmpeg
def test_compress(src, tmp_path):
    out = str(tmp_path / "c.mp4")
    assert run("compress", src, out, timeout=120).returncode == 0
    assert streams_of(out, "video")[0]["codec_name"] == "h264"
    assert streams_of(out, "video")[0]["width"] <= 1280


@needs_ffmpeg
def test_audio(src, tmp_path):
    out = str(tmp_path / "a.mp3")
    assert run("audio", src, out, timeout=120).returncode == 0
    assert os.path.getsize(out) > 1000


@needs_ffmpeg
def test_gif(src, tmp_path):
    out = str(tmp_path / "g.gif")
    assert run("gif", src, out, "--from", "0", "--to", "1", timeout=120).returncode == 0
    assert os.path.getsize(out) > 1000


@needs_ffmpeg
def test_trim(src, tmp_path):
    out = str(tmp_path / "t.mp4")
    assert run("trim", src, out, "--from", "0.5", "--to", "1.5", timeout=120).returncode == 0
    assert abs(duration(out) - 1.0) < 0.3


@needs_ffmpeg
def test_mute(src, tmp_path):
    out = str(tmp_path / "m.mp4")
    assert run("mute", src, out, timeout=120).returncode == 0
    assert streams_of(out, "audio") == []
    assert streams_of(out, "video")


@needs_ffmpeg
def test_thumb(src, tmp_path):
    out = str(tmp_path / "t.jpg")
    assert run("thumb", src, out, "--at", "1", timeout=120).returncode == 0
    assert os.path.getsize(out) > 1000


@needs_ffmpeg
def test_concat(src, tmp_path):
    lst = tmp_path / "list.txt"
    lst.write_text(f"file '{src}'\nfile '{src}'\n")
    out = str(tmp_path / "cc.mp4")
    assert run("concat", str(lst), out, timeout=120).returncode == 0
    assert abs(duration(out) - 4.0) < 0.4


@needs_ffmpeg
def test_resize(src, tmp_path):
    out = str(tmp_path / "r.mp4")
    assert run("resize", src, out, "--width", "160", timeout=120).returncode == 0
    assert streams_of(out, "video")[0]["width"] == 160


@needs_ffmpeg
def test_speed(src, tmp_path):
    out = str(tmp_path / "s.mp4")
    assert run("speed", src, out, "--factor", "2", timeout=120).returncode == 0
    assert abs(duration(out) - 1.0) < 0.3


@needs_ffmpeg
def test_info(src):
    r = run("info", src, timeout=30)
    assert r.returncode == 0
    assert "h264" in r.stdout and "320x240" in r.stdout


def test_no_overwrite_without_force(src, tmp_path):
    out = str(tmp_path / "o.mp4")
    assert run("mute", src, out, timeout=120).returncode == 0
    r = run("mute", src, out, timeout=120)
    assert r.returncode != 0 and "exists" in r.stderr
    assert run("--force", "mute", src, out, timeout=120).returncode == 0


def test_bad_time(src, tmp_path):
    r = run("trim", src, str(tmp_path / "x.mp4"), "--from", "abc", "--to", "5", timeout=30)
    assert r.returncode != 0 and "bad time" in r.stderr


def test_missing_input(tmp_path):
    r = run("info", str(tmp_path / "nope.mp4"), timeout=30)
    assert r.returncode != 0 and "not found" in r.stderr


def test_time_parsing():
    from ffclip import parse_time, atempo_chain
    assert parse_time("90") == 90
    assert parse_time("1:30") == 90
    assert parse_time("01:02:03") == 3723
    assert atempo_chain(4.0) == "atempo=2.0,atempo=2.0"
    assert atempo_chain(0.25) == "atempo=0.5,atempo=0.5"
