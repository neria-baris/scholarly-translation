"""Offline font build, fontTools==4.62.0 (build-only, not runtime dependency).

2026-10-05: instantiate OFL variable fonts at 400/700; convert David CLM
CFF to quadratic TrueType outlines for ReportLab, <= 1 design-unit error.
Original fonts, editable Culmus sources, licenses and hashes accompany outputs.
GPL-2.0 applies to converted David CLM fonts and this conversion, preserving
all copyright notices. Generated-font descriptions identify the modification.
"""
from pathlib import Path
import hashlib
import json

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parent
FIXED_TIME = 3874003200  # 2026-10-05 UTC in the OpenType epoch


def save(font, path):
    font.recalcTimestamp = False
    font['head'].created = font['head'].modified = FIXED_TIME
    font.save(str(ROOT/path))


def static_font(folder, source, family, weight):
    font = TTFont(ROOT/folder/source, recalcTimestamp=False)
    axes = {axis.axisTag:axis.defaultValue for axis in font['fvar'].axes}
    axes['wght'] = weight
    font = instantiateVariableFont(font, axes, inplace=True)
    style = 'Regular' if weight == 400 else 'Bold'
    names = font['name']
    for nameid, value in {1:family,2:style,3:family.replace(' ','')+'-'+style,
                          4:family+' '+style,6:family.replace(' ','')+'-'+style,
                          16:family,17:style,
                          10:'Static weight instance made 2026-10-05 for PDF export; original OFL source bundled.'}.items():
        names.setName(value,nameid,3,1,0x409)
        names.setName(value,nameid,1,0,0)
    save(font,folder+'/'+family.replace(' ','')+'-'+style+'.ttf')


def quadratic_david(style):
    source_name = 'Medium' if style == 'Regular' else 'Bold'
    original = TTFont(ROOT/'culmus/source'/('DavidCLM-'+source_name+'.otf'), recalcTimestamp=False)
    glyph_set = original.getGlyphSet()
    glyphs = {}
    for name in original.getGlyphOrder():
        pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(pen, max_err=1.0, reverse_direction=True))
        glyphs[name] = pen.glyph()
    builder = FontBuilder(original['head'].unitsPerEm, isTTF=True)
    builder.setupGlyphOrder(original.getGlyphOrder())
    builder.setupCharacterMap(original.getBestCmap())
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(original['hmtx'].metrics)
    builder.setupHorizontalHeader(ascent=original['hhea'].ascent, descent=original['hhea'].descent,
                                  lineGap=original['hhea'].lineGap)
    original_names = {n.nameID:n.toUnicode() for n in original['name'].names}
    original_names.update({1:'David CLM PDF',2:style,3:'DavidCLMPDF-'+style,
                           4:'David CLM PDF '+style,6:'DavidCLMPDF-'+style,
                           10:'Converted CFF outlines to quadratic TrueType on 2026-10-05; original Culmus source bundled.'})
    builder.setupNameTable(original_names)
    os2 = original['OS/2']
    builder.setupOS2(sTypoAscender=os2.sTypoAscender,sTypoDescender=os2.sTypoDescender,
                     sTypoLineGap=os2.sTypoLineGap,usWinAscent=os2.usWinAscent,
                     usWinDescent=os2.usWinDescent,usWeightClass=400 if style=='Regular' else 700,
                     fsType=os2.fsType,fsSelection=64 if style=='Regular' else 32)
    builder.setupPost()
    builder.font['head'].macStyle = 0 if style == 'Regular' else 1
    for tag in ['GSUB','GPOS','GDEF']:
        if tag in original: builder.font[tag] = original[tag]
    save(builder.font,'culmus/DavidCLMPDF-'+style+'.ttf')


if __name__ == '__main__':
    for weight in [400,700]:
        static_font('frankruhllibre','FrankRuhlLibre[wght].ttf','Frank Ruhl Libre',weight)
        static_font('notoserifhebrew','NotoSerifHebrew[wdth,wght].ttf','Noto Serif Hebrew',weight)
    for style in ['Regular','Bold']: quadratic_david(style)
    outputs = []
    for path in sorted(ROOT.rglob('*.ttf')):
        outputs.append({'path':path.relative_to(ROOT).as_posix(),
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'size':path.stat().st_size})
    (ROOT/'built_fonts.json').write_text(json.dumps({'fonttools':'4.62.0','files':outputs},indent=2)+'\n')
