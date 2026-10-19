"""Split converted Markdown into chunks that fit BGE-M3.

The stored artifact is Markdown, so this walks headings and paragraphs
instead of Docling's HybridChunker. HybridChunker wants a Docling document
and a Hugging Face tokenizer. Each chunk keeps the headings above it, aims
for about 480 tokens, repeats a short tail from the previous window, and
stays under 1024 tokens. BGE-M3 accepts 8192.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

TARGET_TOKENS = 480
OVERLAP_TOKENS = 64
MAX_TOKENS = 1024

_HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    headings: list[str]


def estimate_tokens(text: str) -> int:
    """Over-estimate tokens so a chunk stays inside the model limit.

    BGE-M3's tokenizer is close to one token per word for ordinary prose, and
    denser for long unbroken strings. Taking the larger of the word count and
    one token per three characters keeps the chunk under the real count.
    """
    stripped = text.strip()
    if not stripped:
        return 0
    return max(len(stripped.split()), math.ceil(len(stripped) / 3))


def chunk_markdown(
    markdown: str,
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> list[TextChunk]:
    """Return embedding-sized chunks with heading context and overlap."""
    if target_tokens < 1 or max_tokens < 1:
        raise ValueError("Chunk size must be positive.")
    if overlap_tokens < 0:
        raise ValueError("Overlap cannot be negative.")
    chunks: list[TextChunk] = []
    headings: list[tuple[int, str]] = []
    for kind, level, text in _blocks(markdown):
        if kind == "heading":
            headings = [(item_level, item_text) for item_level, item_text in headings if item_level < level]
            headings.append((level, text))
            continue
        heading_texts = [item_text for _, item_text in headings]
        prefix = "\n".join(heading_texts)
        budget = max(1, min(target_tokens, max_tokens - estimate_tokens(prefix)))
        for window in _windows(text, budget, overlap_tokens):
            body = f"{prefix}\n{window}" if prefix else window
            body = _shrink_to_limit(body, max_tokens)
            if not body.strip():
                continue
            chunks.append(TextChunk(index=len(chunks), text=body, headings=list(heading_texts)))
    return chunks


def _blocks(markdown: str) -> list[tuple[str, int, str]]:
    blocks: list[tuple[str, int, str]] = []
    buffer: list[str] = []
    in_fence = False
    fence = ""

    def flush() -> None:
        text = "\n".join(buffer).strip()
        buffer.clear()
        if text:
            blocks.append(("body", 0, text))

    for line in markdown.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                flush()
                in_fence = True
                fence = marker
                buffer.append(line)
            elif stripped.startswith(fence):
                buffer.append(line)
                in_fence = False
                flush()
            else:
                buffer.append(line)
            continue
        if in_fence:
            buffer.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            blocks.append(("heading", len(heading.group(1)), heading.group(2).strip()))
            continue
        if not stripped:
            flush()
            continue
        buffer.append(line)
    flush()
    return blocks


def _windows(text: str, budget: int, overlap_tokens: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    windows: list[str] = []
    start = 0
    while start < len(words):
        end = start + 1
        while end < len(words) and estimate_tokens(" ".join(words[start : end + 1])) <= budget:
            end += 1
        windows.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        next_start = _overlap_index(words, end, overlap_tokens)
        if next_start <= start:
            next_start = end
        start = next_start
    return windows


def _overlap_index(words: list[str], end: int, overlap_tokens: int) -> int:
    if overlap_tokens <= 0:
        return end
    start = end
    while start > 0:
        tail = " ".join(words[start - 1 : end])
        if estimate_tokens(tail) > overlap_tokens:
            break
        start -= 1
    return start


def _shrink_to_limit(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    words = text.split()
    while words and estimate_tokens(" ".join(words)) > max_tokens:
        words.pop()
    return " ".join(words)
