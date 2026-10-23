"""Guards for Office files, which are ZIP archives.

Checked from the ZIP central directory before any XML is read: entry count, total
uncompressed size, compression ratio (a decompression bomb), encryption, and that the
archive really contains the part its extension promises.
"""

from __future__ import annotations

import io
import zipfile

from ragkit_server.ingestion.types import ParseError

MAX_ENTRIES = 10_000
MAX_RATIO = 200


def check_ooxml(data: bytes, *, required_prefix: str, label: str, max_uncompressed: int) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ParseError(f"This file is not a valid {label}.") from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES:
            raise ParseError(f"This {label} has too many internal parts to process safely.")
        if any(entry.flag_bits & 0x1 for entry in entries):
            raise ParseError(f"This {label} is password-protected. Remove the password and retry.")
        total = sum(entry.file_size for entry in entries)
        packed = sum(entry.compress_size for entry in entries) or 1
        if total > max_uncompressed or total / packed > MAX_RATIO:
            raise ParseError(f"This {label} expands to more data than RAGKit processes safely.")
        names = {entry.filename for entry in entries}
        if "[Content_Types].xml" not in names or not any(
            name.startswith(required_prefix) for name in names
        ):
            raise ParseError(f"This file does not look like a {label}.")
