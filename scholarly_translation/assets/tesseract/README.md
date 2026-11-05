# Bundled Tesseract OCR engine

Tesseract 5.4.0.20240606 for 64-bit Windows (the UB Mannheim build, leptonica
1.84.1), used by `sources/scanned_ocr.py` to read scanned pages on the user's
computer. Bundling it means scanned books work right after setup, without
administrator rights or a separate install. The language models are in
`../tessdata/` (English, French and Japanese, from tesseract-ocr/tessdata_fast).

## Origin and changes

- **Source:** the official installer
  `tesseract-ocr-w64-setup-5.4.0.20240606.exe` from
  https://github.com/UB-Mannheim/tesseract/releases. Its SHA-256 and the hash of
  every original file are in `sources.json`.
- **Contents:** only `tesseract.exe` and the 26 DLLs it loads (its import
  closure). The training tools, documentation and other files are left out.
- **One change:** the debug information was removed, the same as running
  `strip --strip-debug`. That removed the trailing DWARF sections and the COFF
  symbol table. Code and data are unchanged.
  - **Size:** about 121 MB → 21 MB.
  - **Signatures:** the two signed files also lost their Authenticode table.
    Their certificate had expired before signing, so Windows did not accept
    those signatures anyway.
  - **Check:** the OCR output for English, French and Japanese test pages is
    byte-identical to the original's.
- **Reproduce:** run `python scripts/release/tesseract/build_bundle.py`. It
  rebuilds the files from the official installer and checks each hash.

## Licenses

| Component | License | Text |
|---|---|---|
| Tesseract | Apache-2.0 | `LICENSES/tesseract/LICENSE` |
| OpenSSL (libcrypto), Lerc | Apache-2.0 | `LICENSES/openssl/`, `LICENSES/lerc/` |
| Leptonica, libarchive, libdeflate, Expat, giflib, libwebp/sharpyuv, OpenJPEG, LZ4, Zstandard, libb2, bzip2, libjpeg-turbo, libpng, libtiff, zlib, xz (liblzma), winpthreads | permissive (BSD/MIT/zlib/IJG/0BSD/CC0, see each file) | `LICENSES/<component>/` |
| libstdc++, libgcc | GPL-3.0 with the GCC Runtime Library Exception | `LICENSES/gcc-libs/` |
| libiconv 1.17 | LGPL-2.1-or-later | `LICENSES/libiconv/` |
| JBIG-KIT 2.1 | GPL-2.0-or-later | `LICENSES/jbigkit/COPYING` |

- **Where the license texts come from:** the MSYS2 mingw64 packages that these
  DLLs are built from. Each text's origin is recorded in `sources.json`.
- **Copyleft sources:** the corresponding source code for the copyleft
  components is attached to every release of
  https://github.com/neria-baris/scholarly-translation-app (as
  `libiconv-1.17.tar.gz` and `jbigkit-2.1.tar.gz`).
- **How the app uses the engine:** it runs `tesseract.exe` as a separate
  program. The app's own code does not link against these libraries.
