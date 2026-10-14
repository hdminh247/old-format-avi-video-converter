"""Re-encode any video into the exact AVI layout used by CAO1.avi / CAO2.avi.

Layout: 320x240 MJPEG (baseline 4:2:0, APP0 'AVI1', standard Huffman tables),
1e6/46122 fps, IMA ADPCM mono 22050 Hz with one 512-byte block (1017 samples)
interleaved after every video frame, idx1 with movi-relative offsets.

Converts every video in inputs/ to outputs/<name>.avi.

Usage: python convert_to_cao.py [input_dir] [output_dir]
"""
import io
import struct
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = BASE_DIR / "example" / "CAO1.avi"

W, H = 320, 240
US_PER_FRAME = 46122
SAMPLE_RATE = 22050
BLOCK_ALIGN = 512
SAMPLES_PER_BLOCK = 1017
JPEG_QUALITY = 75
APP0_AVI1 = bytes.fromhex("ffe000104156493100000000000000000000")

STEP_TABLE = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
    3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767,
]
INDEX_TABLE = [-1, -1, -1, -1, 2, 4, 6, 8]


def run_ffmpeg(args):
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    return subprocess.run([exe, "-v", "error", *args], check=True, capture_output=True).stdout


def ima_adpcm_block(samples, predictor, index):
    """Encode SAMPLES_PER_BLOCK mono samples into one 512-byte WAV IMA ADPCM block."""
    predictor = int(samples[0])
    out = bytearray(struct.pack("<hBB", predictor, index, 0))
    nibbles = []
    for s in samples[1:]:
        step = STEP_TABLE[index]
        diff = int(s) - predictor
        code = 0
        if diff < 0:
            code = 8
            diff = -diff
        delta = step >> 3
        if diff >= step:
            code |= 4
            diff -= step
            delta += step
        step >>= 1
        if diff >= step:
            code |= 2
            diff -= step
            delta += step
        step >>= 1
        if diff >= step:
            code |= 1
            delta += step
        predictor += -delta if code & 8 else delta
        predictor = max(-32768, min(32767, predictor))
        index = max(0, min(88, index + INDEX_TABLE[code & 7]))
        nibbles.append(code)
    for i in range(0, len(nibbles), 2):
        out.append(nibbles[i] | (nibbles[i + 1] << 4))
    assert len(out) == BLOCK_ALIGN
    return bytes(out), predictor, index


def encode_jpeg(rgb):
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "JPEG", quality=JPEG_QUALITY, subsampling="4:2:0",
                                     optimize=False, progressive=False)
    data = buf.getvalue()
    # Drop every APPn/COM segment and put the AVI1 APP0 right after SOI.
    i, segs = 2, []
    while data[i] == 0xFF and data[i + 1] != 0xDA:
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        marker = data[i + 1]
        if not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            segs.append(data[i:i + 2 + length])
        i += 2 + length
    return b"\xff\xd8" + APP0_AVI1 + b"".join(segs) + data[i:]


def convert(src, dst, template=DEFAULT_TEMPLATE):
    raw = run_ffmpeg(["-i", src, "-an", "-vf",
                      f"fps=1000000/{US_PER_FRAME},scale={W}:{H}:flags=lanczos",
                      "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
    n = len(frames)

    try:
        pcm = np.frombuffer(run_ffmpeg(["-i", src, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                                        "-f", "s16le", "-"]), "<i2")
    except subprocess.CalledProcessError:
        print("no audio track found, writing silence")
        pcm = np.zeros(0, "<i2")
    pcm = np.pad(pcm, (0, max(0, n * SAMPLES_PER_BLOCK - len(pcm))))[: n * SAMPLES_PER_BLOCK]

    movi, idx = bytearray(b"movi"), bytearray()
    predictor, index = 0, 0
    for k in range(n):
        jpg = encode_jpeg(frames[k])
        padded = jpg + b"\0" * (-len(jpg) % 4)
        idx += struct.pack("<4sIII", b"00dc", 16, len(movi), len(padded))
        movi += struct.pack("<4sI", b"00dc", len(jpg)) + padded

        block, predictor, index = ima_adpcm_block(
            pcm[k * SAMPLES_PER_BLOCK:(k + 1) * SAMPLES_PER_BLOCK], predictor, index)
        idx += struct.pack("<4sIII", b"01wb", 16, len(movi), BLOCK_ALIGN)
        movi += struct.pack("<4sI", b"01wb", BLOCK_ALIGN) + block

    hdr = bytearray(open(template, "rb").read(316))
    assert hdr[12:24] == b"LIST(\x01\x00\x00hdrl" and hdr[288:292] == b"strf"
    struct.pack_into("<I", hdr, 48, n)            # avih dwTotalFrames
    struct.pack_into("<I", hdr, 264, n * 258)     # audio strh dwLength (same quirk as CAO files)
    body = (bytes(hdr[12:]) + struct.pack("<4sI", b"LIST", len(movi)) + movi
            + struct.pack("<4sI", b"idx1", len(idx)) + idx)
    with open(dst, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body) + 4) + b"AVI " + body)
    print(f"wrote {dst}: {n} frames, {n * US_PER_FRAME / 1e6:.1f}s")


def main(input_dir=BASE_DIR / "inputs", output_dir=BASE_DIR / "outputs"):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in input_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    if not sources:
        print(f"no videos found in {input_dir}")
        return
    failed = []
    for src in sources:
        dst = output_dir / (src.stem + ".avi")
        print(f"converting {src.name} ...")
        try:
            convert(src, dst)
        except subprocess.CalledProcessError as e:
            print(f"  failed: {e.stderr.decode(errors='replace').strip()}")
            failed.append(src.name)
    print(f"done: {len(sources) - len(failed)} converted, {len(failed)} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main(*sys.argv[1:])
