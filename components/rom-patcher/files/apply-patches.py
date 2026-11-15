#!/usr/bin/env python3
"""Apply ROM-hack patches (.ips .bps .ups) dropped in <drive>/patches.

The original ROM is never modified: a patched copy is written next to it,
named after the patch file. Applied patches move to patches/applied/.
Usage: apply-patches.py [drive_root]      (default /userdata)
"""
import os, sys, zlib, zipfile, shutil, time

PATCH_EXTS = (".ips", ".bps", ".ups")
SKIP_EXTS = (".txt", ".xml", ".cfg", ".png", ".jpg", ".mp4", ".pdf", ".srm", ".state")


class PatchError(Exception):
    pass


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def u32(b, i):
    return int.from_bytes(b[i:i + 4], "little")


class Reader:
    def __init__(self, data, pos, end):
        self.d, self.i, self.end = data, pos, end

    def vlq(self):
        data, shift = 0, 1
        while True:
            if self.i >= self.end:
                raise PatchError("patch file is truncated")
            x = self.d[self.i]
            self.i += 1
            data += (x & 0x7F) * shift
            if x & 0x80:
                return data
            shift <<= 7
            data += shift


def apply_ips(patch, src):
    if patch[:5] != b"PATCH":
        raise PatchError("not an IPS file")
    out, i = bytearray(src), 5
    while True:
        if i + 3 > len(patch):
            raise PatchError("IPS file is truncated")
        if patch[i:i + 3] == b"EOF":
            i += 3
            break
        off = int.from_bytes(patch[i:i + 3], "big")
        size = int.from_bytes(patch[i + 3:i + 5], "big")
        i += 5
        if size:
            chunk = patch[i:i + size]
            i += size
        else:
            n = int.from_bytes(patch[i:i + 2], "big")
            chunk = patch[i + 2:i + 3] * n
            i += 3
        if off > len(out):
            out.extend(b"\0" * (off - len(out)))
        out[off:off + len(chunk)] = chunk
    if len(patch) - i == 3:
        del out[int.from_bytes(patch[i:i + 3], "big"):]
    return bytes(out)


def bps_header(patch):
    if patch[:4] != b"BPS1" or len(patch) < 16:
        raise PatchError("not a BPS file")
    r = Reader(patch, 4, len(patch) - 12)
    return r, r.vlq(), r.vlq()


def apply_bps(patch, src):
    r, ssize, tsize = bps_header(patch)
    if crc(patch[:-4]) != u32(patch, len(patch) - 4):
        raise PatchError("patch file is corrupt")
    if len(src) != ssize or crc(src) != u32(patch, len(patch) - 12):
        raise PatchError("ROM is not the version this patch was made for")
    meta_len = r.vlq()
    r.i += meta_len
    out, srel, trel = bytearray(), 0, 0
    while r.i < r.end:
        d = r.vlq()
        cmd, n = d & 3, (d >> 2) + 1
        if cmd == 0:
            out += src[len(out):len(out) + n]
        elif cmd == 1:
            out += patch[r.i:r.i + n]
            r.i += n
        else:
            o = r.vlq()
            o = -(o >> 1) if o & 1 else o >> 1
            if cmd == 2:
                srel += o
                out += src[srel:srel + n]
                srel += n
            else:
                trel += o
                for _ in range(n):
                    out.append(out[trel])
                    trel += 1
    if len(out) != tsize or crc(out) != u32(patch, len(patch) - 8):
        raise PatchError("patched result failed its checksum")
    return bytes(out)


def ups_header(patch):
    if patch[:4] != b"UPS1" or len(patch) < 16:
        raise PatchError("not a UPS file")
    r = Reader(patch, 4, len(patch) - 12)
    return r, r.vlq(), r.vlq()


def apply_ups(patch, src):
    r, ssize, tsize = ups_header(patch)
    if crc(patch[:-4]) != u32(patch, len(patch) - 4):
        raise PatchError("patch file is corrupt")
    if len(src) != ssize or crc(src) != u32(patch, len(patch) - 12):
        raise PatchError("ROM is not the version this patch was made for")
    out = bytearray(src[:tsize]) + b"\0" * max(0, tsize - len(src))
    pos = 0
    while r.i < r.end:
        pos += r.vlq()
        while r.i < r.end:
            x = patch[r.i]
            r.i += 1
            if pos < tsize:
                out[pos] ^= x
            pos += 1
            if x == 0:
                break
    if crc(out) != u32(patch, len(patch) - 8):
        raise PatchError("patched result failed its checksum")
    return bytes(out)


def rom_candidates(roms_dir):
    """Yield (system, path, zip member or None, name, size, crc or None)."""
    for system in sorted(os.listdir(roms_dir)):
        sdir = os.path.join(roms_dir, system)
        if not os.path.isdir(sdir):
            continue
        for name in sorted(os.listdir(sdir)):
            p = os.path.join(sdir, name)
            if not os.path.isfile(p) or name.startswith("_") or name.lower().endswith(SKIP_EXTS + PATCH_EXTS):
                continue
            if name.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(p) as z:
                        infos = [i for i in z.infolist() if not i.is_dir()]
                    if len(infos) == 1:
                        yield system, p, infos[0].filename, name, infos[0].file_size, infos[0].CRC
                except (zipfile.BadZipFile, OSError):
                    pass
            else:
                yield system, p, None, name, os.path.getsize(p), None


def read_rom(path, member):
    if member:
        with zipfile.ZipFile(path) as z:
            return z.read(member)
    with open(path, "rb") as f:
        return f.read()


def find_rom(patch_name, patch, roms_dir):
    ext = os.path.splitext(patch_name)[1].lower()
    stem = os.path.splitext(patch_name)[0].lower()
    if ext == ".ips":
        best = None
        for c in rom_candidates(roms_dir):
            rstem = os.path.splitext(c[3])[0].lower()
            if stem.startswith(rstem) and (best is None or len(rstem) > len(os.path.splitext(best[3])[0])):
                best = c
        if not best:
            raise PatchError("no game found whose file name starts this patch's name "
                             "(rename the patch to '<game file name> - <hack name>.ips')")
        return best
    _, ssize, _ = (bps_header if ext == ".bps" else ups_header)(patch)
    want = u32(patch, len(patch) - 12)
    for c in rom_candidates(roms_dir):
        if c[4] != ssize:
            continue
        if (c[5] if c[5] is not None else crc(read_rom(c[1], c[2]))) == want:
            return c
    raise PatchError("no game on the drive matches the exact ROM version this patch needs "
                     "(needs size %d bytes, CRC32 %08X)" % (ssize, want))


def apply_one(patch_path, roms_dir):
    """Returns the path of the patched ROM."""
    name = os.path.basename(patch_path)
    with open(patch_path, "rb") as f:
        patch = f.read()
    system, rpath, member, rname, _, _ = find_rom(name, patch, roms_dir)
    rom_ext = os.path.splitext(member or rname)[1]
    out_path = os.path.join(roms_dir, system, os.path.splitext(name)[0] + rom_ext)
    if os.path.abspath(out_path) == os.path.abspath(rpath):
        out_path = os.path.join(roms_dir, system, os.path.splitext(name)[0] + " (patched)" + rom_ext)
    if os.path.exists(out_path):
        raise PatchError("'%s' already exists" % os.path.basename(out_path))
    fn = {".ips": apply_ips, ".bps": apply_bps, ".ups": apply_ups}[os.path.splitext(name)[1].lower()]
    data = fn(patch, read_rom(rpath, member))
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, out_path)
    return out_path


def main(drive):
    pdir, roms = os.path.join(drive, "patches"), os.path.join(drive, "roms")
    if not os.path.isdir(pdir):
        return 0
    done = os.path.join(pdir, "applied")
    todo = sorted(n for n in os.listdir(pdir) if n.lower().endswith(PATCH_EXTS))
    count = 0
    for n in todo:
        stamp = time.strftime("%Y-%m-%d %H:%M")
        try:
            out = apply_one(os.path.join(pdir, n), roms)
            os.makedirs(done, exist_ok=True)
            shutil.move(os.path.join(pdir, n), os.path.join(done, n))
            msg = "OK    %s -> roms/%s" % (n, os.path.relpath(out, roms))
            count += 1
        except (PatchError, OSError) as e:
            msg = "FAIL  %s: %s" % (n, e)
        print(msg)
        with open(os.path.join(pdir, "patch-log.txt"), "a") as log:
            log.write("%s  %s\n" % (stamp, msg))
    return count


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/userdata")
