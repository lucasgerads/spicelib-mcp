"""
KiCad netlist compatibility fixes for spicelib.

Two known issues affect KiCad-exported netlists. Each fix is a standalone
function so it can be removed independently once fixed upstream.

Upstream issues:
  .title  — https://github.com/nunobrum/spicelib/issues/ (to be filed)
  / nodes — https://github.com/nunobrum/spicelib/issues/ (to be filed)
"""

import re


def fix_title(text: str) -> str:
    """Convert KiCad's `.title <name>` first line to `* <name>`.

    KiCad follows the HSPICE convention of using `.title` as a directive.
    spicelib's detect_encoding() requires the first line to start with `*`
    (Berkeley SPICE / LTspice convention), raising EncodingDetectError otherwise.
    """
    if text.lower().startswith(".title"):
        return "*" + text[6:]
    return text


def fix_node_slashes(text: str) -> str:
    """Remove `/` net-name prefixes throughout the netlist.

    KiCad prefixes hierarchical net names with `/` (e.g. `/out`, `/vcc`).
    spicelib's SpiceEditor component regexes do not allow `/` in node names,
    causing UnrecognizedSyntaxError when editing component values.

    Removes only `/` immediately preceded by whitespace and followed by a
    word character (i.e. net names like `/out`, `/vcc`), leaving path
    separators inside quoted strings (e.g. `.include` paths) untouched.
    """
    return re.sub(r'(?<=\s)/(\w)', r'\1', text)


def apply_all(text: str) -> str:
    """Apply all KiCad compatibility fixes."""
    text = fix_title(text)
    text = fix_node_slashes(text)
    return text
