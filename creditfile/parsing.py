import hashlib
import io
import unicodedata
from pypdf import PdfReader
from .schemas import Block


def normalized_text(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def make_blocks(case_id, document_id, document_type, pages, settings):
    blocks = []
    for page, text in enumerate(pages, 1):
        lines, current = text.splitlines(keepends=True), ""
        chunks = []
        for line in lines:
            if current and len(current) + len(line) > settings.chunk_chars:
                chunks.append(current)
                # Only repeat whole lines, never split financial rows.
                tail = current.splitlines(keepends=True)[-1:]
                current = "".join(tail) if len("".join(tail)) <= settings.overlap else ""
            current += line
        if current.strip():
            chunks.append(current)
        for idx, chunk in enumerate(chunks, 1):
            if chunk.strip():
                blocks.append(
                    Block(
                        case_id=case_id,
                        document_id=document_id,
                        document_type=document_type,
                        page=page,
                        block_id=f"{document_id}_p{page}_b{idx}",
                        text=chunk,
                    )
                )
    return blocks


def parse_pdf(content, case_id, document_id, document_type, settings):
    if not content or len(content) > settings.max_mb * 1024 * 1024:
        raise ValueError(f"Κενό αρχείο ή υπέρβαση {settings.max_mb} MB.")
    if not content.startswith(b"%PDF-"):
        raise ValueError("Το αρχείο δεν είναι PDF.")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("Το PDF είναι κρυπτογραφημένο και απαιτεί κωδικό.")
        if not 1 <= len(reader.pages) <= settings.max_pages:
            raise ValueError(f"Επιτρέπονται 1–{settings.max_pages} σελίδες.")
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:
                pages.append("")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Το PDF είναι κατεστραμμένο ή μη αναγνώσιμο.") from exc
    unreadable = [
        i for i, text in enumerate(pages, 1) if len("".join(c for c in text if c.isalnum())) < 15
    ]
    usable = ["" if i in unreadable else text for i, text in enumerate(pages, 1)]
    return {
        "hash": hashlib.sha256(content).hexdigest(),
        "pages": pages,
        "page_count": len(pages),
        "unreadable_pages": unreadable,
        "status": "unreadable"
        if len(unreadable) == len(pages)
        else "partial"
        if unreadable
        else "readable",
        "blocks": [
            b.model_dump()
            for b in make_blocks(case_id, document_id, document_type, usable, settings)
        ],
    }
