"""Build code-native pixel art inspired by the user's gold/cream book reference.

No raster input or image processing: snapped SVG geometry, 32x40 pixels/frame.
Opening 0..7, page-turn loop 8..31, closing 32..39. Run from any directory.
"""
from pathlib import Path
from math import cos, pi, sin

FRAME_WIDTH, FRAME_HEIGHT, FRAME_COUNT = 32, 40, 40
COLORS = {
    'cover': '#896b12', 'edge': '#b39732', 'dark': '#604a09',
    'paper': '#e9e6b0', 'light': '#f4f1cb', 'shade': '#c7c887',
    'ink': '#a8ad78', 'spine': '#74762f',
}


def polygon(points, color):
    coords = ' '.join(f'{round(x)},{round(y)}' for x, y in points)
    return f'<polygon fill="{COLORS[color]}" points="{coords}"/>'


def rect(x, y, width, height, color):
    return (f'<rect x="{round(x)}" y="{round(y)}" width="{round(width)}" '
            f'height="{round(height)}" fill="{COLORS[color]}"/>')


def closed():
    # A narrow spine on the left and the opening/fore-edge on the right.
    return ''.join([
        polygon([(10,7),(23,5),(23,32),(10,34)], 'dark'),
        polygon([(11,8),(22,6),(22,31),(11,33)], 'cover'),
        rect(10,8,2,24,'edge'),
        polygon([(22,7),(24,8),(24,31),(22,32)], 'shade'),
        rect(23,9,1,20,'light'),
        polygon([(12,31),(22,29),(22,31),(12,33)], 'edge'),
        rect(14,12,6,1,'dark'),rect(14,14,4,1,'dark'),
        rect(14,27,6,1,'edge'),
    ])


def open_book(amount=1, turn=None):
    # Both covers stay on a shared baseline. The vertical gutter is the spine.
    extent = 2 + 12*amount
    left, right = 16-extent, 16+extent
    elements = [
        polygon([(left,9),(15,11),(17,11),(right,9),(right,34),
                 (17,36),(15,36),(left,34)], 'dark'),
        polygon([(left,8),(15,10),(17,10),(right,8),(right,33),
                 (17,35),(15,35),(left,33)], 'edge'),
        polygon([(left+1,7),(15,10),(15,33),(left+1,30)], 'shade'),
        polygon([(left+2,6),(15,9),(15,32),(left+2,29)], 'paper'),
        polygon([(17,9),(right-2,6),(right-2,29),(17,32)], 'light'),
        polygon([(right-2,6),(right-1,7),(right-1,30),(right-2,29)], 'shade'),
        rect(15,10,2,24,'spine'),rect(16,10,1,23,'shade'),
    ]
    if amount > .45:
        # Sparse pixel marks reflect the quiet speckled pages in the reference.
        for side in (-1,1):
            for dx, y in ((4,13),(8,17),(5,23),(10,26),(7,11)):
                x=16+side*dx*amount
                elements.append(rect(x,y,1,1,'ink'))
    if turn is not None:
        # Page rotates around the gutter, sweeps right to left, then settles.
        span=(extent-2)*cos(pi*turn)
        tip=16+span
        lift=5*sin(pi*turn)
        elements.append(polygon([(16,9),(tip,6-lift),(tip,29-lift),(16,33)],
                                'light' if span>=0 else 'paper'))
        elements.append(polygon([(tip,6-lift),(tip+1,7-lift),(tip+1,30-lift),
                                 (tip,29-lift)], 'shade'))
        if abs(span)>4:
            elements.append(rect(16+span*.55,14-lift*.55,1,1,'ink'))
            elements.append(rect(16+span*.72,24-lift*.72,1,1,'ink'))
    return ''.join(elements)


def build():
    first=closed()
    opening=[first]+[open_book(n/7) for n in range(1,8)]
    turns=[open_book(turn=n/24) for n in range(24)]
    # Mirroring the opening in reverse makes the final opening side face left.
    closing=[f'<g transform="translate(32 0) scale(-1 1)">{frame}</g>'
             for frame in reversed(opening)]
    frames=opening+turns+closing
    assert len(frames)==FRAME_COUNT
    groups='\n'.join(f'<g id="frame-{n}" transform="translate({n*32} 0)">{frame}</g>'
                     for n,frame in enumerate(frames))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="40" '
            f'viewBox="0 0 1280 40" shape-rendering="crispEdges">\n'
            '<title>Gold book: open, turn pages, close</title>\n'+groups+'\n</svg>\n')


if __name__ == '__main__':
    target=Path(__file__).resolve().parents[1]/'scholarly_translation/assets/book-sprite.svg'
    target.write_text(build(),encoding='utf-8',newline='\n')
    print('Built 40 frames at 32x40:',target.name)
