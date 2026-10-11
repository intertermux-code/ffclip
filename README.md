# ffclip

[![ci](https://github.com/intertermux-code/ffclip/actions/workflows/ci.yml/badge.svg)](https://github.com/intertermux-code/ffclip/actions)
[![pypi](https://img.shields.io/pypi/v/ffclip.svg)](https://pypi.org/project/ffclip/)

Humane ffmpeg. The 10 media recipes everyone googles, with sane defaults —
a thin wrapper with zero dependencies. ffmpeg and ffprobe do the real work
(they must be installed and on your `PATH`).

```sh
pip install ffclip

ffclip compress input.mp4 output.mp4        # shrink for sharing (H.264/AAC)
ffclip audio    input.mp4 output.mp3        # extract audio
ffclip gif      input.mp4 out.gif --from 10 --to 15
ffclip trim     input.mp4 out.mp4 --from 1:30 --to 2:45
ffclip mute     input.mp4 out.mp4           # strip the audio track
ffclip thumb    input.mp4 shot.jpg --at 5
ffclip concat   list.txt out.mp4            # join same-codec files
ffclip resize   input.mp4 out.mp4 --width 1280
ffclip speed    input.mp4 out.mp4 --factor 2 # video + audio stay in sync
ffclip info     input.mp4                   # human-readable summary
```

Times accept seconds (`90`, `90.5`) or `HH:MM:SS`. ffmpeg's own progress
passes straight through to your terminal.

## Notes

- `gif` uses the two-pass palette method, so the output doesn't look like
  it was dithered by a potato — unlike most one-liner recipes.
- `speed` chains `atempo` filters, so factors outside 0.5–2 (like 4x) work
  and audio stays pitched correctly relative to video.
- `trim` re-encodes for frame accuracy; if you want instant lossless cuts
  and can live with keyframe granularity, that's a different tool.
- Outputs are never overwritten unless you pass `--force` / `-y`.
- `concat` takes a text file with one `file 'path'` per line (ffmpeg
  concat demuxer format) and joins same-codec files without re-encoding.

POSIX only (Linux, macOS). Python 3.9+.

## License

MIT.
