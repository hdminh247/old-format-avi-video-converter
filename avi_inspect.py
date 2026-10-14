import struct
import sys


def walk(f, end, depth, out):
    while f.tell() + 8 <= end:
        pos = f.tell()
        fourcc = f.read(4)
        size = struct.unpack("<I", f.read(4))[0]
        ind = "  " * depth
        if fourcc in (b"RIFF", b"LIST"):
            kind = f.read(4)
            out.append(f"{ind}{fourcc.decode()} '{kind.decode(errors='replace')}' size={size} @ {pos}")
            if kind == b"movi":
                # summarize chunk ids in movi
                counts = {}
                sub_end = pos + 8 + size
                first = []
                while f.tell() + 8 <= sub_end:
                    cid = f.read(4)
                    csz = struct.unpack("<I", f.read(4))[0]
                    if cid == b"LIST":
                        f.read(4)
                        continue
                    counts[cid] = counts.get(cid, 0) + 1
                    if len(first) < 2 and cid.endswith(b"dc"):
                        first.append(f.read(min(csz, 64)))
                        f.seek(-len(first[-1]), 1)
                    f.seek(csz + (csz & 1), 1)
                out.append(f"{ind}  movi chunks: {{{', '.join(f'{k.decode(errors='replace')}: {v}' for k, v in counts.items())}}}")
                for b in first:
                    out.append(f"{ind}  first frame bytes: {b[:64].hex()}")
                f.seek(sub_end + (size & 1))
            else:
                walk(f, pos + 8 + size, depth + 1, out)
                f.seek(pos + 8 + size + (size & 1))
        else:
            data = f.read(size)
            desc = ""
            if fourcc == b"avih":
                v = struct.unpack("<10I", data[:40])
                desc = (f"usPerFrame={v[0]} maxBps={v[1]} flags=0x{v[3]:x} totalFrames={v[4]} "
                        f"initFrames={v[5]} streams={v[6]} bufSize={v[7]} {v[8]}x{v[9]}")
            elif fourcc == b"strh":
                t, h = data[:4], data[4:8]
                v = struct.unpack("<IHHIIIIIIII", data[8:48])
                desc = (f"type={t} handler={h} flags={v[0]} scale={v[4]} rate={v[5]} start={v[6]} "
                        f"length={v[7]} bufSize={v[8]} quality={v[9]} sampleSize={v[10]}")
            elif fourcc == b"strf" and len(data) >= 40:
                v = struct.unpack("<IiiHH4sIiiII", data[:40])
                desc = (f"BITMAPINFOHEADER size={v[0]} {v[1]}x{v[2]} planes={v[3]} bitCount={v[4]} "
                        f"compression={v[5]} sizeImage={v[6]} extra={data[40:].hex()}")
            elif fourcc == b"strf":
                desc = data.hex()
            elif fourcc in (b"ISFT", b"strn", b"INAM"):
                desc = data.rstrip(b"\0").decode(errors="replace")
            elif fourcc == b"idx1":
                desc = f"entries={size // 16}"
            out.append(f"{ind}{fourcc.decode(errors='replace')} size={size} {desc}")
            if size & 1:
                f.read(1)


for path in sys.argv[1:]:
    with open(path, "rb") as f:
        f.seek(0, 2)
        total = f.tell()
        f.seek(0)
        out = []
        walk(f, total, 0, out)
    print(f"===== {path} (file size {total})")
    print("\n".join(out))
