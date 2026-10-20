"""Filesystem-safe naming shared by the handlers and the report generator.

Style and effect names come straight from design decks, and the suite also
runs on Windows, whose rules are the strictest of the platforms we target.
"""
import re

# Characters Windows rejects in a path component, plus ASCII control chars
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Device names Windows reserves regardless of extension (CON.pptx is still CON)
_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}


def safe_path_name(name, replacement='_'):
    """Make one path component valid on Windows, macOS and Linux.

    Only the characters Windows forbids are replaced, so a name that is already
    valid comes back unchanged and folders created before this existed still
    match. Spaces, brackets, commas and non-ASCII text (Chinese style names) are
    all kept.

    Args:
        name: A single folder or file name (not a full path).
        replacement: What each invalid character becomes.

    Returns:
        str: The safe name; '_' if nothing usable is left.
    """
    safe = _INVALID_CHARS.sub(replacement, str(name))
    # Windows silently drops trailing dots and spaces, so "Style." and "Style"
    # would collide
    safe = safe.rstrip('. ')
    if safe.split('.')[0].upper() in _RESERVED_NAMES:
        safe = f'{replacement}{safe}'
    return safe or replacement
