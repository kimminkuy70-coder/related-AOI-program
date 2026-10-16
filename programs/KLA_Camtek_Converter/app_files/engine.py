# -*- coding: utf-8 -*-
"""KLA <-> Camtek conversion engine (skeleton).

The conversion direction and the file formats are not settled yet (see
docs/kla_camtek_converter_plan.md). app.py only calls discover(), inspect() and convert(),
so the formats can be filled in here without touching the window code.
Import heavy packages (openpyxl, numpy, ...) inside functions: engine is imported at startup.
"""
from pathlib import Path

# File suffixes the folder scan picks up, e.g. ('.klarf', '.000') - decided from sample files.
SOURCE_SUFFIXES = ()


def discover(root, suffixes=SOURCE_SUFFIXES):
    """Source files under root (sub-folders included), sorted like Explorer by path."""
    root = Path(root)
    found = [p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in suffixes and not p.name.startswith('~$')]
    return sorted(found, key=lambda p: str(p).lower())


def inspect(path):
    """Header summary of one source file for the file list (lot, wafer, device, counts...)."""
    raise NotImplementedError('변환 형식이 아직 정해지지 않았습니다.')


def convert(source, target):
    """Write the converted file of source to target and return {'output': str(path)}."""
    raise NotImplementedError('변환 형식이 아직 정해지지 않았습니다.')
