"""A small QR encoder for the pairing link: byte mode, error correction M, versions 1-10. No dependencies."""

from __future__ import annotations

# version -> (ec codewords per block, [(blocks, data codewords per block), ...]), level M
_BLOCKS = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i], _LOG[_x] = _x, _i
    _x = (_x << 1) ^ (0x11D if _x & 0x80 else 0)
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _ec(data: list[int], n: int) -> list[int]:
    gen = [1]
    for i in range(n):
        gen = [a ^ _mul(b, _EXP[i]) for a, b in zip(gen + [0], [0] + gen, strict=True)]
    rem = list(data) + [0] * n
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j, g in enumerate(gen):
                rem[i + j] ^= _mul(g, coef)
    return rem[len(data):]


def _bch(value: int, poly: int, bits: int) -> int:
    rem = value << (poly.bit_length() - 1)
    while rem.bit_length() >= poly.bit_length():
        rem ^= poly << (rem.bit_length() - poly.bit_length())
    return (value << (poly.bit_length() - 1)) | rem if bits else rem


def _codewords(text: bytes, version: int) -> list[int]:
    ec_len, groups = _BLOCKS[version]
    capacity = sum(n * size for n, size in groups)
    bits = [0, 1, 0, 0] + [int(b) for b in format(len(text), "016b" if version >= 10 else "08b")]
    for byte in text:
        bits += [int(b) for b in format(byte, "08b")]
    bits += [0] * min(4, capacity * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    data += [0xEC, 0x11] * ((capacity - len(data)) // 2 + 1)
    data = data[:capacity]
    blocks, at = [], 0
    for n, size in groups:
        for _ in range(n):
            blocks.append(data[at:at + size])
            at += size
    ecs = [_ec(b, ec_len) for b in blocks]
    out = [b[i] for i in range(max(map(len, blocks))) for b in blocks if i < len(b)]
    return out + [e[i] for i in range(ec_len) for e in ecs]


def _version(length: int) -> int:
    for version, (_ec_len, groups) in _BLOCKS.items():
        head = 12 if version < 10 else 20
        if head + 8 * length <= 8 * sum(n * size for n, size in groups):
            return version
    raise ValueError("text too long for a version 10 QR code")


def _penalty(m: list[list[int]]) -> int:
    n, score = len(m), 0
    for grid in (m, [list(col) for col in zip(*m, strict=True)]):
        for row in grid:
            run = 1
            for i in range(1, n + 1):
                if i < n and row[i] == row[i - 1]:
                    run += 1
                    continue
                score += run - 2 if run >= 5 else 0
                run = 1
            text = "".join(map(str, row))
            score += 40 * (text.count("10111010000") + text.count("00001011101"))
    score += 3 * sum(1 for y in range(n - 1) for x in range(n - 1)
                     if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1])
    dark = sum(map(sum, m))
    return score + 10 * (abs(dark * 20 - n * n * 10) // (n * n))


def encode(text: str) -> list[list[bool]]:
    """The QR modules of ``text``, rows of booleans (True = dark), without the quiet zone."""
    raw = text.encode("utf-8")
    version = _version(len(raw))
    n = 17 + 4 * version
    grid = [[0] * n for _ in range(n)]
    fixed = [[False] * n for _ in range(n)]

    def put(x: int, y: int, dark: bool) -> None:
        grid[y][x], fixed[y][x] = int(dark), True

    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    d = max(abs(dx), abs(dy))
                    put(x, y, d not in (2, 4))
    for i in range(8, n - 8):
        put(i, 6, i % 2 == 0)
        put(6, i, i % 2 == 0)
    spots = _ALIGN[version]
    for ay in spots:
        for ax in spots:
            if (ax, ay) in ((6, 6), (6, spots[-1]), (spots[-1], 6)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
    put(8, n - 8, True)
    for i in range(9):
        fixed[8][i] = fixed[i][8] = True
    for i in range(8):
        fixed[8][n - 1 - i] = fixed[n - 1 - i][8] = True
    if version >= 7:
        info = _bch(version, 0x1F25, 1)
        for i in range(18):
            bit = (info >> i) & 1
            put(n - 11 + i % 3, i // 3, bit)
            put(i // 3, n - 11 + i % 3, bit)

    bits = [(cw >> (7 - i)) & 1 for cw in _codewords(raw, version) for i in range(8)]
    at, right = 0, n - 1
    while right >= 1:
        if right == 6:
            right -= 1
        for vert in range(n):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = n - 1 - vert if upward else vert
                if not fixed[y][x]:
                    grid[y][x] = bits[at] if at < len(bits) else 0
                    at += 1
        right -= 2

    masks = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)
    best = None
    for index, mask in enumerate(masks):
        m = [[grid[y][x] ^ (not fixed[y][x] and mask(x, y)) for x in range(n)] for y in range(n)]
        fmt = _bch(index, 0x537, 1) ^ 0x5412
        for i in range(15):
            bit = (fmt >> i) & 1
            first = (8, i) if i < 6 else (8, i + 1) if i < 8 else (7, 8) if i == 8 else (14 - i, 8)
            second = (n - 1 - i, 8) if i < 8 else (8, n - 15 + i)
            for x, y in (first, second):
                m[y][x] = bit
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return [[bool(v) for v in row] for row in best[1]]


def text_art(text: str) -> str:
    """The code in half-block characters for a terminal, quiet zone included."""
    m = encode(text)
    n = len(m) + 4
    full = [[False] * n for _ in range(2)] + [[False, False] + row + [False, False] for row in m] \
        + [[False] * n for _ in range(3)]
    chars = {(False, False): "█", (True, False): "▄", (False, True): "▀", (True, True): " "}
    return "\n".join("".join(chars[(full[y][x], full[y + 1][x])] for x in range(n)) for y in range(0, n + 1, 2))
