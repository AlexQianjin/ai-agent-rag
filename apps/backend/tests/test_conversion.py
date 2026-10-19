"""Convert sample files through the shared Markdown interface."""

from pathlib import Path

import pytest

from backend.conversion import DocumentRejected, convert_to_markdown, validate_upload


def test_txt_and_markdown_are_read_directly(tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("Hello from TXT\n", encoding="utf-8")
    page = tmp_path / "page.md"
    page.write_text("# Hello from Markdown\n", encoding="utf-8")

    assert convert_to_markdown(notes, notes.name) == "Hello from TXT\n"
    assert convert_to_markdown(page, page.name) == "# Hello from Markdown\n"
    assert validate_upload(notes.name, notes.stat().st_size) == "text/plain"
    assert validate_upload("chapter.markdown", 12) == "text/markdown"


def test_pdf_and_docx_use_docling(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    docx_path = tmp_path / "sample.docx"
    _write_pdf(pdf_path, "Hello from PDF")
    _write_docx(docx_path, "Hello from DOCX")

    pdf_markdown = convert_to_markdown(pdf_path, pdf_path.name)
    docx_markdown = convert_to_markdown(docx_path, docx_path.name)

    assert "Hello from PDF" in pdf_markdown
    assert "Hello from DOCX" in docx_markdown


def test_unsupported_and_oversized_uploads_are_rejected() -> None:
    with pytest.raises(DocumentRejected, match="PDF, DOCX, TXT, or Markdown") as unsupported:
        validate_upload("scan.png", 10)
    assert unsupported.value.status_code == 400

    with pytest.raises(DocumentRejected, match="20 MB") as too_large:
        validate_upload("notes.txt", 20 * 1024 * 1024 + 1)
    assert too_large.value.status_code == 413

    with pytest.raises(DocumentRejected, match="empty"):
        validate_upload("notes.txt", 0)


def _write_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode("ascii")
        output += body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode("ascii")
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(output)


def _write_docx(path: Path, text: str) -> None:
    import zipfile

    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)
