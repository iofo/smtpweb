import logging
from pathlib import Path

import pypdfium2 as pdfium

log = logging.getLogger(__name__)

THUMBNAIL_MAX_WIDTH = 320


def generate_pdf_thumbnail(pdf_path: Path, thumb_path: Path) -> bool:
    """Render the first page of the PDF at pdf_path to a PNG at
    thumb_path. Returns whether it succeeded — a corrupted or
    unparseable "PDF" just means no thumbnail, not a hard failure."""
    try:
        with pdfium.PdfDocument(str(pdf_path)) as pdf:
            page = pdf[0]
            width, _height = page.get_size()
            scale = THUMBNAIL_MAX_WIDTH / width if width else 1.0
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(thumb_path, "PNG")
        return True
    except Exception:
        log.warning("Failed to generate PDF thumbnail for %s", pdf_path, exc_info=True)
        return False
