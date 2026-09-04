#!/usr/bin/env python3
"""
Draw the application icons.

Written with nothing but zlib and struct from the standard library, so the
icons can be redrawn on any machine without installing an image package.
Run it from the project root:  python3 tools/make_icons.py
"""

import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HERE, "chartered_book", "web", "static", "icons")

NAVY = (29, 53, 87, 255)
DEEP = (22, 41, 68, 255)
PAPER = (255, 255, 255, 255)
RULE = (203, 213, 225, 255)
ACCENT = (198, 156, 74, 255)
CLEAR = (0, 0, 0, 0)


def write_png(path, width, height, pixels):
    """pixels is a list of rows, each row a list of (r, g, b, a) tuples."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type none
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(body)


def blend(under, over):
    """Put one colour over another, honouring the alpha of the top one."""
    alpha = over[3] / 255.0
    if alpha >= 1:
        return over
    if alpha <= 0:
        return under
    return tuple(int(round(over[i] * alpha + under[i] * (1 - alpha))) for i in range(3)) + (255,)


def rounded_rect(canvas, x0, y0, x1, y1, radius, colour, size):
    """Fill a rounded rectangle, softening the edge so it does not look jagged."""
    for y in range(max(0, int(y0)), min(size, int(y1) + 1)):
        for x in range(max(0, int(x0)), min(size, int(x1) + 1)):
            dx = 0.0
            dy = 0.0
            if x < x0 + radius:
                dx = (x0 + radius) - x
            elif x > x1 - radius:
                dx = x - (x1 - radius)
            if y < y0 + radius:
                dy = (y0 + radius) - y
            elif y > y1 - radius:
                dy = y - (y1 - radius)
            if dx == 0 and dy == 0:
                canvas[y][x] = blend(canvas[y][x], colour)
                continue
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= radius - 0.5:
                canvas[y][x] = blend(canvas[y][x], colour)
            elif distance < radius + 0.5:
                edge = radius + 0.5 - distance
                faded = colour[:3] + (int(colour[3] * max(0.0, min(1.0, edge))),)
                canvas[y][x] = blend(canvas[y][x], faded)


def disc(canvas, cx, cy, radius, colour, size):
    """Stamp a filled circle with a soft edge. The unit a pen stroke is made of."""
    top = max(0, int(cy - radius - 1))
    bottom = min(size - 1, int(cy + radius + 1))
    left = max(0, int(cx - radius - 1))
    right = min(size - 1, int(cx + radius + 1))
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            distance = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
            if distance <= radius - 0.5:
                canvas[y][x] = blend(canvas[y][x], colour)
            elif distance < radius + 0.5:
                edge = radius + 0.5 - distance
                faded = colour[:3] + (int(colour[3] * max(0.0, min(1.0, edge))),)
                canvas[y][x] = blend(canvas[y][x], faded)


def stroke_arc(canvas, cx, cy, radius, start_deg, end_deg, width, colour, size):
    """
    Draw an arc as a pen stroke of a given width, by walking along it and
    stamping a disc at every step. Round ends come free, which is what makes the
    letter look drawn rather than cut out.
    """
    import math
    steps = max(24, int(abs(end_deg - start_deg) * radius / 60.0) + 24)
    for index in range(steps + 1):
        portion = index / float(steps)
        angle = math.radians(start_deg + (end_deg - start_deg) * portion)
        disc(canvas, cx + radius * math.cos(angle), cy + radius * math.sin(angle),
             width / 2.0, colour, size)


def draw(size, padded=True):
    """
    The mark is the S of Saphal, drawn as a single stroke on a navy panel.

    The letter is built from two arcs that meet in the middle, the top one
    curving up and to the left and the bottom one down and to the right, which
    is how an S is written rather than how it is typed. A gold underline sits
    beneath it, the same gold as the column rule on an invoice.
    """
    canvas = [[CLEAR for _ in range(size)] for _ in range(size)]
    unit = size / 512.0

    if padded:
        rounded_rect(canvas, 0, 0, size - 1, size - 1, 112 * unit, NAVY, size)
    else:
        for y in range(size):
            for x in range(size):
                canvas[y][x] = NAVY

    centre = size / 2.0
    # The letter stands 4 bowls plus a stroke tall, so the bowl has to stay
    # small enough that the whole thing sits inside the panel with air around
    # it. An icon that touches its own edges reads as a mistake at any size.
    bowl = 72 * unit          # radius of each half of the letter
    stroke = 46 * unit        # how thick the pen is
    lift = 26 * unit          # the whole letter sits a little above centre

    # Top half: starts at the upper right, over the top, down the left, to the
    # middle. Bottom half: out of the middle, round the right, down to the
    # lower left. Together they make the one continuous stroke of an S.
    # The terminals run a little past the quarter, which opens the letter out
    # and stops the two ends looking cut off.
    stroke_arc(canvas, centre, centre - bowl - lift, bowl, -18, -270, stroke, PAPER, size)
    stroke_arc(canvas, centre, centre + bowl - lift, bowl, -90, 162, stroke, PAPER, size)

    # The gold rule, the same one that separates the amount column on a bill.
    rule_width = 132 * unit
    rule_y = centre + 2 * bowl - lift + stroke / 2 + 34 * unit
    rounded_rect(canvas, centre - rule_width / 2, rule_y,
                 centre + rule_width / 2, rule_y + 15 * unit, 8 * unit, ACCENT, size)
    return canvas


def _old_draw(size, padded=True):
    """
    The mark is a ledger page: a navy panel holding a white sheet with ruled
    lines and a gold column rule down the amount side.
    """
    canvas = [[CLEAR for _ in range(size)] for _ in range(size)]
    unit = size / 512.0

    if padded:
        rounded_rect(canvas, 0, 0, size - 1, size - 1, 112 * unit, NAVY, size)
        margin = 96 * unit
    else:
        for y in range(size):
            for x in range(size):
                canvas[y][x] = NAVY
        margin = 96 * unit

    # A slightly darker band down the left, like the spine of a bound book.
    rounded_rect(canvas, margin - 26 * unit, margin - 18 * unit,
                 margin + 6 * unit, size - margin + 18 * unit, 12 * unit, DEEP, size)

    # The page.
    page_left = margin
    page_right = size - margin
    page_top = margin - 18 * unit
    page_bottom = size - margin + 18 * unit
    rounded_rect(canvas, page_left, page_top, page_right, page_bottom, 16 * unit, PAPER, size)

    # The gold rule that separates particulars from the amount column.
    column = page_right - 96 * unit
    rounded_rect(canvas, column, page_top + 26 * unit, column + 7 * unit,
                 page_bottom - 26 * unit, 3 * unit, ACCENT, size)

    # Ruled lines, with the entries getting shorter the way a ledger looks.
    widths = (0.86, 0.70, 0.78, 0.58, 0.66)
    first = page_top + 62 * unit
    gap = (page_bottom - page_top - 118 * unit) / (len(widths) - 1)
    for index, portion in enumerate(widths):
        y = first + gap * index
        line_end = page_left + (column - page_left - 34 * unit) * portion
        rounded_rect(canvas, page_left + 30 * unit, y, line_end, y + 15 * unit,
                     7 * unit, RULE, size)
        # The figure sitting in the amount column.
        amount_width = 52 * unit if index % 2 == 0 else 40 * unit
        rounded_rect(canvas, page_right - 30 * unit - amount_width, y,
                     page_right - 30 * unit, y + 15 * unit, 7 * unit,
                     RULE if index < len(widths) - 1 else NAVY, size)
    return canvas


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    made = []
    for size in (32, 64, 180, 192, 512):
        canvas = draw(size)
        path = os.path.join(OUT_DIR, "icon-%d.png" % size)
        write_png(path, size, size, canvas)
        made.append((path, os.path.getsize(path)))
    # A maskable icon fills the whole square, because Android crops to a circle.
    canvas = draw(512, padded=False)
    path = os.path.join(OUT_DIR, "icon-maskable-512.png")
    write_png(path, 512, 512, canvas)
    made.append((path, os.path.getsize(path)))
    for path, size in made:
        print("  %-52s %6d bytes" % (os.path.relpath(path, HERE), size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
