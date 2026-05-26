"""
Log ingestion service.

Responsibilities:
- Read raw log files from disk
- Auto-detect format and parse each line into a LogEntry
- Chunk a list of LogEntry objects into overlapping text windows
  suitable for embedding
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import List

from app.core.logger import get_logger
from app.models.log_entry import LogEntry
from app.utils.log_parser import auto_detect_and_parse

logger = get_logger(__name__)


def load_log_file(file_path: str) -> List[LogEntry]:
    """
    Read *file_path*, parse every line, and return a list of LogEntry objects.

    - Skips blank lines and comment lines (starting with #).
    - Skips malformed lines with a WARNING log but continues processing.
    - Supports .log and .txt extensions.

    Args:
        file_path: Absolute or relative path to the log file.

    Returns:
        List of successfully parsed LogEntry objects (may be empty).

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If the file extension is not .log or .txt.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")

    if path.suffix.lower() not in (".log", ".txt"):
        raise ValueError(
            f"Unsupported file type '{path.suffix}'. Only .log and .txt are accepted."
        )

    entries: List[LogEntry] = []
    skipped = 0
    total_lines = 0

    logger.info(f"Loading log file: {path} ({path.stat().st_size / 1024:.1f} KB)")

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.rstrip("\n\r")
            total_lines += 1

            # Skip blank / comment lines
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            try:
                parsed = auto_detect_and_parse(line)
                if parsed is None:
                    logger.warning(f"Line {lineno}: parser returned None, skipping: {line[:80]!r}")
                    skipped += 1
                    continue

                entry = LogEntry.from_parsed_dict(parsed)
                entries.append(entry)

            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Line {lineno}: failed to parse ({exc}), skipping: {line[:80]!r}")
                skipped += 1

    logger.info(
        f"Loaded {len(entries)} entries from {total_lines} lines "
        f"({skipped} skipped) in {path.name}"
    )
    return entries


def chunk_logs(
    entries: List[LogEntry],
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """
    Group *entries* into overlapping text chunks for embedding.

    Each chunk is a concatenation of multiple log entries' text representations.
    The total character length of each chunk is approximately *chunk_size*,
    with *overlap* characters shared between adjacent chunks.

    Args:
        entries:    List of LogEntry objects to chunk.
        chunk_size: Target maximum character length per chunk.
        overlap:    Number of characters to carry over from the previous chunk.

    Returns:
        List of text strings, each representing one chunk.
    """
    if not entries:
        return []

    chunks: List[str] = []
    current_lines: List[str] = []
    current_length = 0

    for entry in entries:
        line_text = entry.to_chunk_text()
        line_len = len(line_text)

        # If a single line exceeds chunk_size, wrap it alone
        if line_len >= chunk_size:
            # Flush current buffer first
            if current_lines:
                chunks.append("\n".join(current_lines))
                # Keep overlap tail
                current_lines, current_length = _trim_to_overlap(current_lines, overlap)

            # Add the long line as its own chunk (possibly split further)
            for sub_chunk in textwrap.wrap(line_text, width=chunk_size):
                chunks.append(sub_chunk)
            continue

        # Would adding this line exceed the chunk size?
        if current_length + line_len + 1 > chunk_size and current_lines:
            chunks.append("\n".join(current_lines))
            # Keep tail lines for overlap
            current_lines, current_length = _trim_to_overlap(current_lines, overlap)

        current_lines.append(line_text)
        current_length += line_len + 1  # +1 for newline

    # Flush remaining lines
    if current_lines:
        chunks.append("\n".join(current_lines))

    logger.debug(
        f"Chunked {len(entries)} entries into {len(chunks)} chunks "
        f"(chunk_size={chunk_size}, overlap={overlap})"
    )
    return chunks


def load_and_chunk(
    file_path: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> tuple[List[LogEntry], List[str]]:
    """
    Convenience wrapper: load a file and immediately chunk it.

    Returns:
        Tuple of (entries, chunks).
    """
    entries = load_log_file(file_path)
    chunks = chunk_logs(entries, chunk_size=chunk_size, overlap=overlap)
    return entries, chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _trim_to_overlap(lines: List[str], overlap: int) -> tuple[List[str], int]:
    """
    Remove lines from the front of *lines* until the total character count
    is <= *overlap*, preserving the tail for context continuity.
    """
    if overlap <= 0:
        return [], 0

    total = sum(len(l) + 1 for l in lines)
    while lines and total > overlap:
        removed = lines.pop(0)
        total -= len(removed) + 1

    return lines, total
