"""Remove debug information from MinGW-built 64-bit Windows PE files.

Equivalent to ``strip --strip-debug`` for the Tesseract bundle: drops the
trailing discardable sections with long (``/N``) names that MinGW uses for
DWARF, the COFF symbol table and, if present, the Authenticode certificate
table (the signature can no longer match once bytes are removed). Code and
data sections, the import/export tables and resources are not touched.

Build-time tool only (needs ``pefile``: ``pip install pefile==2024.8.26``).

    python strip_pe.py SOURCE_DIR TARGET_DIR NAME [NAME ...]
"""

from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

DISCARDABLE = 0x02000000
SECURITY = 4  # IMAGE_DIRECTORY_ENTRY_SECURITY
PE32_PLUS = 0x20B


class StripError(Exception):
    pass


def strip_file(source: Path, target: Path) -> tuple[int, int]:
    """Write a stripped copy of ``source`` to ``target``; return (old, new) sizes."""
    import pefile

    data = bytearray(Path(source).read_bytes())
    pe = pefile.PE(data=bytes(data), fast_load=True)
    if pe.OPTIONAL_HEADER.Magic != PE32_PLUS:
        raise StripError(f"{source.name}: not a 64-bit (PE32+) image")
    sections = pe.sections
    debug = [s.Name.startswith(b"/") and bool(s.Characteristics & DISCARDABLE) for s in sections]
    keep = len(sections)
    while keep and debug[keep - 1]:
        keep -= 1
    if keep == len(sections):
        shutil.copyfile(source, target)
        return len(data), len(data)
    if any(debug[:keep]):
        raise StripError(f"{source.name}: debug sections are not all at the end")
    end = max(s.PointerToRawData + s.SizeOfRawData for s in sections[:keep])
    if any(s.PointerToRawData < end for s in sections[keep:]):
        raise StripError(f"{source.name}: debug section data precedes kept data")
    directories = pe.OPTIONAL_HEADER.DATA_DIRECTORY
    for index, entry in enumerate(directories):
        if index == SECURITY or not (entry.VirtualAddress and entry.Size):
            continue
        if not any(s.VirtualAddress <= entry.VirtualAddress < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)
                   for s in sections[:keep]):
            raise StripError(f"{source.name}: data directory {index} lies in a removed section")
    signed = bool(directories[SECURITY].Size)
    if signed and directories[SECURITY].VirtualAddress < end:  # a file offset for this entry
        raise StripError(f"{source.name}: certificate table overlaps kept data")

    alignment = pe.OPTIONAL_HEADER.SectionAlignment
    last = sections[keep - 1]
    size_of_image = -(-(last.VirtualAddress + max(last.Misc_VirtualSize, 1)) // alignment) * alignment
    file_header = pe.FILE_HEADER.get_file_offset()
    optional_header = pe.OPTIONAL_HEADER.get_file_offset()
    struct.pack_into("<H", data, file_header + 2, keep)            # NumberOfSections
    struct.pack_into("<II", data, file_header + 8, 0, 0)           # PointerToSymbolTable, NumberOfSymbols
    struct.pack_into("<I", data, optional_header + 56, size_of_image)
    struct.pack_into("<I", data, optional_header + 64, 0)          # CheckSum (not checked for user-mode images)
    if signed:
        struct.pack_into("<II", data, optional_header + 112 + SECURITY * 8, 0, 0)
    for section in sections[keep:]:
        offset = section.get_file_offset()
        data[offset:offset + 40] = bytes(40)
    Path(target).write_bytes(bytes(data[:end]))
    return len(data), end


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        print(__doc__)
        return 2
    source, target = Path(argv[0]), Path(argv[1])
    target.mkdir(parents=True, exist_ok=True)
    for name in argv[2:]:
        old, new = strip_file(source / name, target / name)
        print(f"{name:28} {old / 1e6:8.2f} -> {new / 1e6:7.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
