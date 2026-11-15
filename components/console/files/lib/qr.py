"""A small QR code maker: enough for a web address, nothing more.

    qr.matrix("http://192.168.1.20:8377/k/4f9c")   rows of True (dark) / False (light)

Batocera has no QR library, and all EmuBox needs is to show a short address for
a phone to scan (the phone keyboard, phonekeys.py). So this makes the plainest
kind: bytes, the lowest level of error correction, sizes 1 to 5 (up to 106
bytes), always the same mask. Any phone camera reads it.
"""
from __future__ import annotations

# For each size (version): how many bytes of data, and how many of error correction.
SIZES = {1: (19, 7), 2: (34, 10), 3: (55, 15), 4: (80, 20), 5: (108, 26)}

# Arithmetic in the field the error correction uses (GF(256), polynomial 0x11D).
EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def correction(data: list[int], count: int) -> list[int]:
    """The error-correction bytes for a block of data (Reed-Solomon)."""
    generator = [1]
    for i in range(count):
        generator = [(generator[j] if j < len(generator) else 0) ^
                     (EXP[LOG[generator[j - 1]] + i] if j and generator[j - 1] else 0)
                     for j in range(len(generator) + 1)]
    rest = [0] * count
    for byte in data:
        factor = byte ^ rest[0]
        rest = rest[1:] + [0]
        if factor:
            for j in range(count):
                if generator[j + 1]:
                    rest[j] ^= EXP[LOG[generator[j + 1]] + LOG[factor]]
    return rest


def codewords(text: bytes) -> tuple[int, list[int]]:
    """The size to use and every byte that goes into the picture: data, then correction."""
    for version, (room, extra) in SIZES.items():
        if len(text) + 2 <= room:   # two bytes go on saying "bytes" and how many
            break
    else:
        raise ValueError("too long for a QR code of this kind (106 bytes at most)")
    bits = [0, 1, 0, 0] + [len(text) >> i & 1 for i in range(7, -1, -1)]
    for byte in text:
        bits += [byte >> i & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, room * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    data += [(0xEC, 0x11)[i % 2] for i in range(room - len(data))]
    return version, data + correction(data, extra)


def format_bits() -> int:
    """The 15 bits that tell a reader the correction level (lowest) and the mask (the first)."""
    value = 0b01 << 3 | 0
    rest = value << 10
    for shift in range(4, -1, -1):
        if rest >> (shift + 10) & 1:
            rest ^= 0x537 << shift
    return (value << 10 | rest) ^ 0x5412


def matrix(text: str | bytes) -> list[list[bool]]:
    """The QR code for a text, as rows of modules: True is dark."""
    version, stream = codewords(text.encode() if isinstance(text, str) else text)
    size = 17 + 4 * version
    grid: list[list[bool | None]] = [[None] * size for _ in range(size)]

    def square(top: int, left: int) -> None:   # a corner's finder pattern, with its light border
        for r in range(-1, 8):
            for c in range(-1, 8):
                if 0 <= top + r < size and 0 <= left + c < size:
                    ring = max(abs(r - 3), abs(c - 3))
                    grid[top + r][left + c] = ring != 2 and ring <= 3

    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        square(top, left)
    if version > 1:                              # the small square near the fourth corner
        centre = 4 * version + 10
        for r in range(-2, 3):
            for c in range(-2, 3):
                grid[centre + r][centre + c] = max(abs(r), abs(c)) != 1
    for i in range(8, size - 8):                 # the two dotted lines between the corners
        grid[6][i] = grid[i][6] = i % 2 == 0
    fmt = format_bits()
    for i in range(15):
        dark = bool(fmt >> i & 1)
        grid[i if i < 6 else i + 1 if i < 8 else size - 15 + i][8] = dark
        grid[8][size - i - 1 if i < 8 else 15 - i if i < 9 else 14 - i] = dark
    grid[size - 8][8] = True

    bits = [byte >> i & 1 for byte in stream for i in range(7, -1, -1)]
    at, row, step = 0, size - 1, -1
    for right in range(size - 1, 0, -2):         # two columns at a time, snaking up and down
        if right <= 6:
            right -= 1                           # the dotted column is skipped
        while True:
            for col in (right, right - 1):
                if grid[row][col] is None:
                    dark = bool(bits[at]) if at < len(bits) else False
                    at += 1
                    grid[row][col] = dark != ((row + col) % 2 == 0)   # the mask
            row += step
            if not 0 <= row < size:
                row -= step
                step = -step
                break
    return [[bool(cell) for cell in line] for line in grid]


def image(text: str, scale: int = 8, border: int = 4):
    """The QR code as a Pillow image, dark on white, with the quiet border readers need."""
    from PIL import Image
    modules = matrix(text)
    size = len(modules) + 2 * border
    picture = Image.new("1", (size, size), 1)
    for r, line in enumerate(modules):
        for c, dark in enumerate(line):
            if dark:
                picture.putpixel((c + border, r + border), 0)
    return picture.resize((size * scale, size * scale))
