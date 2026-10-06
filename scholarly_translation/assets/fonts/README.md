# Bundled PDF typefaces

These are local runtime assets: exporting or switching a PDF font performs no
network download and no model request. Both regular and bold faces include
Hebrew letters, Latin ASCII and digits. The closed selection IDs are
`david-libre`, `hadasim-clm`, `noto-serif-hebrew`, `frank-ruhl-libre`, `david-clm`.
Existing calls without a selection retain the earlier host-font behaviour.

## Sources, permissions and provenance

- David Libre: Google Fonts distribution, SIL OFL 1.1, verbatim regular/bold
  binaries; license in `davidlibre/OFL.txt`.
- Noto Serif Hebrew: Google Fonts distribution, SIL OFL 1.1; 400/700 weight
  instances of the supplied variable font at its default width. Original
  variable font and license in `notoserifhebrew/`.
- Frank Ruhl Libre: Google Fonts distribution, SIL OFL 1.1; 400/700 weight
  instances. Original variable font and license in `frankruhllibre/`.
- Hadasim CLM: Culmus/CTAN distribution, GPL 2 with the explicit document font
  embedding exception stated in `culmus/LICENSE.txt`; verbatim regular/bold
  binaries. Editable SFD sources in `culmus/source/`.
- David CLM: Culmus/CTAN distribution, GPL 2 and the separate Bitstream Charter
  copyright/permission notice. Both notices are retained in `culmus/`. Unlike
  Hadasim, the upstream David section **does not identify a document embedding
  exception**. The UI/export metadata records that distinction; this repository
  does not assert unrestricted redistribution of documents embedding David CLM.
  Original CFF OTF binaries, editable SFD sources and supporting feature files
  accompany the converted fonts in `culmus/source/`.

- Noto Sans Math and Noto Sans: Google Fonts distribution, SIL OFL 1.1. Not
  selectable; they are the PDF glyph fallback (in that order) for math
  operators, Greek, super/subscripts and symbols the Hebrew fonts lack. Noto
  Sans Math is verbatim; Noto Sans is a 400-weight instance of the bundled
  variable font. Licenses in `notosansmath/` and `notosans/`.

Primary Culmus notices: [upstream LICENSE](https://sources.debian.org/src/culmus/0.140-3/LICENSE),
[GPL 2](https://sources.debian.org/src/culmus/0.140-3/GNU-GPL),
[Bitstream notice](https://sources.debian.org/src/culmus/0.140-3/LICENSE-BITSTREAM).
Font licenses govern these assets, separately from project source code.

`sources.json` records download URLs, pinned Google Fonts revision, byte sizes
and SHA-256 hashes of original assets/notices. `built_fonts.json` records hashes
of all runtime TTFs and original variable TTFs. These files contain only public
font provenance. There are no user inputs or credentials.

## Rebuilding (not needed at runtime)

With Python and build-only `fonttools==4.62.0`, run `python build_fonts.py` from
any directory. The build reads only local originals, produces static instances,
and converts David's CFF cubic outlines to TrueType quadratic outlines at at
most one design-unit approximation error. A fixed OpenType timestamp makes the
result reproducible. The generated David family is internally named
`David CLM PDF` to identify the conversion; the UI retains the requested family
label. Copyright and license notices remain intact. Conversion date: 2026-10-05.

This exporter retains its documented limited bidi routine; font availability
does not imply full Biblical mark shaping or a general Unicode bidi engine.
