"""
KiCad netlist compatibility fixes for spicelib.

Known issue:
  / nodes — SpiceEditor's component regexes do not allow `/` in node names.
             Remove this module once fixed upstream in spicelib.

Note: the `.title` first-line issue is handled by passing encoding="utf-8"
to SpiceEditor, bypassing spicelib's encoding auto-detection. A proper fix
is planned upstream (per spicelib maintainer).
"""

import re


def fix_node_slashes(text: str) -> str:
    """Remove `/` net-name prefixes throughout the netlist.

    KiCad prefixes hierarchical net names with `/` (e.g. `/out`, `/vcc`).
    spicelib's SpiceEditor component regexes do not allow `/` in node names,
    causing UnrecognizedSyntaxError when editing component values.

    Removes only `/` immediately followed by a word character, leaving
    any other use of `/` (e.g. in comments or .include paths) untouched.
    """
    return re.sub(r'/(\w)', r'\1', text)


def apply_all(text: str) -> str:
    """Apply all KiCad compatibility fixes."""
    return fix_node_slashes(text)
