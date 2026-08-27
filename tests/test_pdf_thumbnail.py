from smtpweb.common.pdf_thumbnail import generate_pdf_thumbnail

from .conftest import MINIMAL_PDF_BYTES


def test_generates_valid_png_thumbnail(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(MINIMAL_PDF_BYTES)
    thumb_path = tmp_path / "thumbnails" / "doc.pdf.png"

    ok = generate_pdf_thumbnail(pdf_path, thumb_path)

    assert ok is True
    assert thumb_path.exists()
    assert thumb_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_thumbnail_width_matches_target(tmp_path):
    from PIL import Image

    from smtpweb.common.pdf_thumbnail import THUMBNAIL_MAX_WIDTH

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(MINIMAL_PDF_BYTES)
    thumb_path = tmp_path / "doc.pdf.png"

    generate_pdf_thumbnail(pdf_path, thumb_path)

    with Image.open(thumb_path) as img:
        assert img.width == THUMBNAIL_MAX_WIDTH


def test_corrupted_pdf_returns_false_not_raises(tmp_path):
    pdf_path = tmp_path / "not-really-a-pdf.pdf"
    pdf_path.write_bytes(b"this is not a pdf at all, just some bytes")
    thumb_path = tmp_path / "thumbnails" / "not-really-a-pdf.pdf.png"

    ok = generate_pdf_thumbnail(pdf_path, thumb_path)

    assert ok is False
    assert not thumb_path.exists()


def test_missing_source_file_returns_false_not_raises(tmp_path):
    ok = generate_pdf_thumbnail(tmp_path / "does-not-exist.pdf", tmp_path / "out.png")
    assert ok is False
