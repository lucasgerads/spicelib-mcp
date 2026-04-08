"""
Minimal reproduction of spicelib failing to parse KiCad netlists.

KiCad exports netlists with `.title <name>` as the first line, following
the HSPICE convention. spicelib's detect_encoding() expects the first line
to start with `*` (Berkeley SPICE convention), causing an EncodingDetectError.

Run with:
    uv run python test_kicad_title.py
"""

from spicelib.editor.spice_editor import SpiceEditor

print("Testing standard.cir (first line starts with *)...")
try:
    SpiceEditor("standard.cir")
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")

print("Testing kicad.cir (first line starts with .title)...")
try:
    SpiceEditor("kicad.cir")
    print("  OK")
except Exception as e:
    print(f"  FAILED: {e}")
