# Convert a video to the player's AVI format

The media player only plays AVI files laid out exactly like `example/CAO1.avi` /
`example/CAO2.avi`. `convert_to_cao.py` re-encodes any normal video (MP4, MKV, MOV,
AVI, ...) into that layout.

## Folders

| Folder | Contents |
|---|---|
| `inputs/` | Put the videos to convert here |
| `outputs/` | Converted `.avi` files are written here |
| `example/` | Reference files that play on the device (`CAO1.avi` ... `CAO4.avi`) |

## Target format

| Property | Value |
|---|---|
| Container | AVI (RIFF), legacy `idx1` index |
| Video | MJPEG, 320x240, baseline JPEG 4:2:0, quality 75, `AVI1` APP0 header |
| Frame rate | 21.68 fps (46122 µs per frame) |
| Audio | IMA ADPCM, mono, 22050 Hz, 512-byte blocks (1017 samples) |
| Interleave | One video frame (`00dc`) followed by one audio block (`01wb`) |

The file header is copied from `example/CAO1.avi`, so keep that file in place.

## One-time setup

Requires Python 3. From this folder:

```bash
python3 -m venv .venv
.venv/bin/pip install imageio-ffmpeg pillow numpy
```

`imageio-ffmpeg` ships its own ffmpeg binary, so ffmpeg does not need to be installed
on the system. Skip this step if `.venv` already exists.

## Convert videos

1. Copy your videos into `inputs/`.
2. Run:

   ```bash
   .venv/bin/python convert_to_cao.py
   ```

3. Copy the files from `outputs/` to the player.

Each `inputs/<name>.<ext>` becomes `outputs/<name>.avi` (existing files are
overwritten). Example output:

```
converting movie.mp4 ...
wrote /Volumes/DATA/Workspace/Videos/outputs/movie.avi: 883 frames, 40.7s
done: 1 converted, 0 failed
```

Files ffmpeg cannot read are reported as failed and skipped; the rest are still
converted. Other folders can be used instead of the defaults:

```bash
.venv/bin/python convert_to_cao.py /path/to/videos /path/to/converted
```

## Notes

- The video is stretched to 320x240. For widescreen sources, crop or letterbox to 4:3
  first if you want to keep the aspect ratio, e.g.:

  ```bash
  FF=$(.venv/bin/python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
  $FF -i movie.mp4 -vf "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2" -c:a aac inputs/movie.mp4
  ```

  Then run the converter as usual.

- If the source has no audio track, a silent track is written automatically.

- Frames are decoded fully into memory (about 230 KB per frame, roughly 300 MB per
  minute of video), so split very long videos before converting.

## Checking a file

`avi_inspect.py` prints the AVI header of any file, which is useful to compare a
converted file against `example/CAO1.avi`:

```bash
python3 avi_inspect.py example/CAO1.avi outputs/movie.avi
```
