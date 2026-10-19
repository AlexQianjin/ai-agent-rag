"""Turn an uploaded file into Markdown.

PDF and DOCX go through Docling. TXT and Markdown are read as UTF-8. Every
supported type uses `convert_to_markdown`, so callers do not branch on format.
"""

from __future__ import annotations

import os
from pathlib import Path

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}

_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
_DOCLING_SUFFIXES = {".pdf", ".docx"}


class DocumentRejected(Exception):
    """The upload cannot be accepted."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def mime_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        return _MIME_BY_SUFFIX[suffix]
    except KeyError as exc:
        raise DocumentRejected(
            "Upload a PDF, DOCX, TXT, or Markdown file.",
            400,
        ) from exc


def validate_upload(filename: str, size: int, *, limit: int = MAX_UPLOAD_BYTES) -> str:
    """Check the name and size. Return the mime type callers should store."""
    if size <= 0:
        raise DocumentRejected("The file is empty.", 400)
    if size > limit:
        raise DocumentRejected("File is larger than 20 MB.", 413)
    return mime_type_for(filename)


def convert_to_markdown(path: Path, filename: str) -> str:
    """Convert a file that has already passed `validate_upload`."""
    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return _read_text(path)
    if suffix in _DOCLING_SUFFIXES:
        return _docling_markdown(path)
    raise DocumentRejected("Upload a PDF, DOCX, TXT, or Markdown file.", 400)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise DocumentRejected("The text file is not valid UTF-8.", 400) from exc


_converter = None


def _docling_markdown(path: Path) -> str:
    result = _converter_for().convert(path)
    if result.status.value == "failure":
        raise DocumentRejected("Docling could not convert this file.", 400)
    markdown = result.document.export_to_markdown()
    if not isinstance(markdown, str) or not markdown.strip():
        raise DocumentRejected("Docling did not return Markdown.", 400)
    return markdown


def _converter_for():
    global _converter
    if _converter is not None:
        return _converter
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH", "").strip()
    pipeline_options = PdfPipelineOptions()
    if artifacts:
        pipeline_options.artifacts_path = Path(artifacts)
    # CPU image: skip the OCR model download. PDFs that already have a text
    # layer still convert. Scanned pages can be enabled later.
    pipeline_options.do_ocr = False
    _converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
    return _converter
