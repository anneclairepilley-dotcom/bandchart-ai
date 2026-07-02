"""Renders a MusicXML file to PDF sheet music.

Pipeline: verovio engraves the MusicXML to SVG pages (pip-only, no system
binaries), cairosvg converts each page to PDF, pypdf merges the pages.
cairosvg needs the libcairo2 system library — present by default in GitHub
Codespaces and most Linux/macOS setups; the import happens lazily inside
musicxml_to_pdf() so a missing library can never stop the backend from
starting, only fail the PDF request with an actionable message.
"""

from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

VEROVIO_OPTIONS = {
    "scale": 50,
    "footer": "none",
    "adjustPageHeight": False,
}

# Verovio's font resources use process-global state that breaks when toolkits
# are created repeatedly across the server's worker threads (font loading
# starts failing after a few requests). Create one toolkit lazily and
# serialize all use of it.
_toolkit = None
_toolkit_lock = threading.Lock()


def _get_toolkit():
    global _toolkit
    if _toolkit is None:
        import verovio

        tk = verovio.toolkit()
        tk.setOptions(VEROVIO_OPTIONS)
        _toolkit = tk
    return _toolkit


def _strip_metronome_directions(musicxml_text: str) -> str:
    """Remove <direction> blocks holding <metronome> marks.

    The metronome's note glyph needs a music text font that cairosvg can't
    load, so it renders as an empty box in the PDF. The tempo stays in the
    .musicxml download for MuseScore users; only the PDF drops it.
    """
    root = ET.fromstring(musicxml_text)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "direction" and child.find(".//metronome") is not None:
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def musicxml_to_pdf(musicxml_path: Path, pdf_path: Path) -> Path:
    """Engrave musicxml_path as PDF sheet music at pdf_path."""
    try:
        import cairosvg
    except OSError as exc:
        raise RuntimeError(
            "The PDF engine needs the 'cairo' system library, which wasn't found. "
            "Run: sudo apt-get update && sudo apt-get install -y libcairo2 — then "
            "restart the backend and try again."
        ) from exc
    from pypdf import PdfReader, PdfWriter

    xml_text = _strip_metronome_directions(musicxml_path.read_text())

    with _toolkit_lock:
        toolkit = _get_toolkit()
        if not toolkit.loadData(xml_text):
            raise RuntimeError("The sheet-music engraver couldn't read the MusicXML data")
        page_count = toolkit.getPageCount()
        if page_count < 1:
            raise RuntimeError("The sheet-music engraver produced no pages")
        svgs = [toolkit.renderToSVG(page) for page in range(1, page_count + 1)]

    writer = PdfWriter()
    for svg in svgs:
        page_pdf = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
        writer.append(PdfReader(BytesIO(page_pdf)))

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path
