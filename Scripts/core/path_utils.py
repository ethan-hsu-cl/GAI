"""Filesystem-safe naming shared by the handlers and the report generator.

Style and effect names come straight from design decks, and the suite also
runs on Windows, whose rules are the strictest of the platforms we target.
"""
import hashlib
import re
from pathlib import Path

# Characters Windows rejects in a path component, plus ASCII control chars
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Device names Windows reserves regardless of extension (CON.pptx is still CON)
_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}

# Windows' MAX_PATH is 260 including the terminating NUL. Without the
# LongPathsEnabled policy, a longer path can't be created or opened.
MAX_PATH = 259

# Room kept after a source file's stem for what handlers append to it. The
# longest is "_generated_10_metadata.json" (27).
SUFFIX_ROOM = 30

# Longest output subfolder a handler writes into, next to Source
LONGEST_OUTPUT_DIR = 'Generated_Output'


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


def name_room(*folders):
    """How long a file name can be in every one of folders under MAX_PATH.

    Measured from the absolute path on the machine running, since that's
    where the limit applies.
    """
    return MAX_PATH - 1 - max(len(str(Path(f).absolute())) for f in folders)


def fit_name(name, max_len):
    """Cut name to max_len characters, or return it unchanged if it fits.

    A cut name ends in "~" and a hash of the full name, so two long names that
    share a prefix stay distinct and the same name is always cut the same way
    (resume checks find it again).

    Raises:
        ValueError: If max_len can't hold even the hash, i.e. the folder alone
            is nearly at the limit.
    """
    if len(name) <= max_len:
        return name
    digest = hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]
    keep = max_len - len(digest) - 1
    if keep < 1:
        raise ValueError(
            f"Folder path is too long: no room for a file name under Windows' "
            f"{MAX_PATH}-character limit. Move the folder closer to the drive root."
        )
    return f"{name[:keep]}~{digest}"
