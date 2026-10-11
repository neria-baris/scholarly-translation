"""Build code-native pixel art modelled on the user's gold/cream book reference.

No raster input or image processing: snapped SVG geometry, 32x40 pixels/frame.
Opening 0..11 (cover swings on its hinge, then a block of pages flips over),
page-turn loop 12..35, closing 36..47 (mirrored opening ending on the back
cover). Run from any directory.
"""
from pathlib import Path
from math import cos, pi, sin

FRAME_WIDTH, FRAME_HEIGHT = 32, 40
OPENING, LOOP = 12, 24
FRAME_COUNT = OPENING + LOOP + OPENING
COLORS = {
    'out': '#442604', 'spine': '#5c3e04', 'cover': '#6c5204', 'label': '#7c5a1c',
    'p1': '#d4de94', 'p2': '#c4c474', 'p3': '#aca664', 'p4': '#9c8e54',
}
GUTTER, PAGE, TOP, BOTTOM = 16, 14, 9, 31


def polygon(points, color):
    coords = ' '.join(f'{round(x)},{round(y)}' for x, y in points)
    return f'<polygon fill="{COLORS[color]}" points="{coords}"/>'


def rect(x, y, width, height, color):
    return (f'<rect x="{round(x)}" y="{round(y)}" width="{round(width)}" '
            f'height="{round(height)}" fill="{COLORS[color]}"/>')


def mirror(svg):
    return f'<g transform="translate({FRAME_WIDTH} 0) scale(-1 1)">{svg}</g>'


def ease(t):
    return t*t*(3-2*t)


def closed(back=False):
    # Front view tilted slightly down: cover, spine on the left, page edges
    # and the back board showing along the bottom.
    parts = [
        rect(7, 8, 18, 28, 'out'),
        rect(8, 33, 16, 2, 'cover'),
        rect(9, 31, 15, 2, 'p1'), rect(9, 32, 15, 1, 'p3'), rect(10, 31, 1, 1, 'p2'),
        rect(9, 7, 15, 24, 'cover'), rect(9, 7, 15, 1, 'label'),
        rect(7, 7, 2, 26, 'spine'), rect(8, 8, 1, 24, 'label'),
        rect(24, 8, 1, 24, 'out'),
    ]
    if back:
        parts += [rect(14, 18, 1, 1, 'label'), rect(18, 18, 1, 1, 'label')]
    else:
        parts += [rect(12, 11, 9, 4, 'spine'), rect(13, 12, 7, 2, 'label'),
                  rect(12, 27, 9, 1, 'spine')]
    return ''.join(parts)


def page_stack(x, color='p1'):
    # One side of the open book: a stack of pages on its board, gutter at x.
    return ''.join([
        rect(x, 33, PAGE+1, 2, 'cover'), rect(x, 35, PAGE+1, 1, 'out'),
        rect(x, TOP, PAGE, BOTTOM-TOP, color),
        rect(x, BOTTOM, PAGE+1, 1, 'p2'), rect(x, BOTTOM+1, PAGE+1, 1, 'p3'),
        rect(x+PAGE, TOP+1, 1, BOTTOM-TOP, 'p3'),
        rect(x+PAGE-1, TOP, 1, 1, 'p2'),
        rect(x, TOP, 2, BOTTOM-TOP, 'p2'), rect(x, TOP-1, 1, BOTTOM-TOP+2, 'p3'),
        rect(x+5, 14, 1, 1, 'p4'), rect(x+10, 18, 1, 1, 'p4'),
        rect(x+6, 24, 1, 1, 'p4'), rect(x+11, 27, 1, 1, 'p4'),
    ])


def inside_cover(x):
    # Left half once the front cover lies flat: the bare inside of the board.
    return ''.join([rect(x, TOP-1, PAGE+1, 27, 'cover'), rect(x, 35, PAGE+1, 1, 'out'),
                    rect(x+PAGE, TOP-1, 1, 27, 'spine')])


def leaf(hinge, u, thick=1, top=TOP, bottom=BOTTOM, width=PAGE):
    # A page (or a block of pages) rotating about the gutter, right to left.
    span = width*cos(pi*u)
    lift = 5*sin(pi*u)
    tip = hinge+span
    face = 'p1' if span >= 0 else 'p2'
    step = 1 if span >= 0 else -1
    parts = []
    if abs(span) > 2:
        # Shadow the turning sheet casts on the page beneath it.
        shadow_x = hinge+span*.45
        parts.append(polygon([(hinge, bottom-6), (shadow_x, bottom-2),
                              (shadow_x, bottom), (hinge, bottom)], 'p3'))
    parts.append(polygon([(hinge, top), (tip, top-lift), (tip, bottom-lift),
                          (hinge, bottom)], face))
    parts.append(polygon([(tip, top-lift), (tip+step*thick, top-lift+1),
                          (tip+step*thick, bottom-lift+1), (tip, bottom-lift)], 'p3'))
    if abs(span) > 5:
        parts.append(rect(hinge+span*.5, 15-lift*.5, 1, 1, 'p4'))
        parts.append(rect(hinge+span*.7, 23-lift*.7, 1, 1, 'p4'))
    return ''.join(parts)


def opening(n, back=False):
    if n == 0:
        return closed(back)
    if n <= 6:
        # The front cover swings toward the viewer and over to the left while
        # the hinge slides to the centre of the frame.
        t = n/6
        hinge = 9+(GUTTER-9)*ease(t)
        span = PAGE*cos(pi*t)
        lift = 6*sin(pi*t)
        tip = hinge+span
        parts = [page_stack(hinge)]
        if span < 0:
            parts.insert(0, rect(hinge-1, TOP, 2, 26, 'spine'))
        parts.append(polygon([(hinge, 7), (tip, 7-lift), (tip, 33-lift), (hinge, 33)],
                             'cover'))
        edge = 1 if span >= 0 else -1
        parts.append(polygon([(tip, 7-lift), (tip+edge, 8-lift), (tip+edge, 33-lift),
                              (tip, 32-lift)], 'out'))
        if span > 4 and not back:
            parts.append(polygon([(hinge+span*.2, 11-lift*.2), (hinge+span*.85, 11-lift*.85),
                                  (hinge+span*.85, 14-lift*.85), (hinge+span*.2, 14-lift*.2)],
                                 'spine'))
        return ''.join(parts)
    # A thick block of pages follows the cover across.
    u = (n-6)/(OPENING-6)
    if n == OPENING-1:
        return open_spread()
    return inside_cover(1)+page_stack(GUTTER)+leaf(GUTTER, u, thick=2)


def open_spread():
    return mirror(page_stack(GUTTER))+page_stack(GUTTER)


def turn(n):
    # Two page turns per loop, each with a short rest.
    u = (n % 12)/10
    frame = open_spread()
    return frame if u <= 0 or u >= 1 else frame+leaf(GUTTER, u)


def build():
    opened = [opening(n) for n in range(OPENING)]
    turns = [turn(n) for n in range(LOOP)]
    # Reversing a mirrored opening flips the pages back, then closes the back
    # cover over them, so the book ends showing its back.
    closing = [mirror(opening(n, back=True)) for n in reversed(range(OPENING))]
    frames = opened+turns+closing
    assert len(frames) == FRAME_COUNT
    groups = '\n'.join(f'<g id="frame-{n}" transform="translate({n*FRAME_WIDTH} 0)">{frame}</g>'
                       for n, frame in enumerate(frames))
    width = FRAME_COUNT*FRAME_WIDTH
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{FRAME_HEIGHT}" '
            f'viewBox="0 0 {width} {FRAME_HEIGHT}" shape-rendering="crispEdges">\n'
            '<title>Gold book: open, turn pages, close</title>\n'+groups+'\n</svg>\n')


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1]/'scholarly_translation/assets/book-sprite.svg'
    target.write_bytes(build().encode('utf-8'))
    print(f'Built {FRAME_COUNT} frames at {FRAME_WIDTH}x{FRAME_HEIGHT}:', target.name)
