"""Local PDF geometry and rendering. No model imports, no remote assets."""

import base64
import pymupdf
from .parsing import normalized_text


def row_rectangles(page, quote):
    """Find a unique physical row using local word coordinates.

    PDF text-stream order often writes whole columns before the next column.
    Matching the visible row avoids fabricating geometry for table citations.
    """
    rows = []
    for word in sorted(page.get_text("words"), key=lambda w: (round((w[1] + w[3]) / 2, 1), w[0])):
        center = (word[1] + word[3]) / 2
        row = next((r for r in rows if abs(r[0] - center) < 2.5), None)
        if row is None:
            row = [center, []]
            rows.append(row)
        row[1].append(word)
    matches = []
    for _, words in rows:
        words.sort(key=lambda w: w[0])
        text = ""
        spans = []
        for w in words:
            start = len(text)
            text += normalized_text(w[4])
            spans.append((start, len(text), w))
            text += " "
        start = text.find(quote)
        if start >= 0:
            if text.find(quote, start + 1) >= 0:
                return []
            selected = [
                pymupdf.Rect(w[:4]) for a, b, w in spans if b > start and a < start + len(quote)
            ]
            matches.append(selected)
    return matches[0] if len(matches) == 1 else []


def source_geometry(content, evidence, block, raw_value=None):
    source = dict(evidence)
    source.update(
        rectangles=[],
        value_rectangles=[],
        geometry_status="no_exact_highlight",
        parser="PyMuPDF " + pymupdf.VersionBind,
    )
    if (
        evidence["document_id"] != block["document_id"]
        or evidence["block_id"] != block["block_id"]
        or evidence["page"] != block["page"]
        or normalized_text(evidence["quote"]) not in normalized_text(block["text"])
    ):
        return source
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        page = pdf[evidence["page"] - 1]
        source.update(
            page_width=page.rect.width, page_height=page.rect.height, rotation=page.rotation
        )
        quote = normalized_text(evidence["quote"])
        # Ambiguous repeated quotes never select the first amount on the page.
        rects = page.search_for(quote) if normalized_text(page.get_text()).count(quote) == 1 else []
        if not rects:
            rects = row_rectangles(page, quote)
        if not rects:
            return source
        source["rectangles"] = [list(r * page.rotation_matrix) for r in rects]
        source["geometry_status"] = "quote_located"
        if raw_value and quote.count(normalized_text(raw_value)) == 1:
            values = [
                r for r in page.search_for(raw_value) if any(outer.contains(r) for outer in rects)
            ]
            if len(values) == 1:
                source["value_rectangles"] = [list(values[0] * page.rotation_matrix)]
                source["geometry_status"] = "value_located"
        return source


def enrich_sources(result, documents, pdf_reader):
    """Attach local geometry once, before storage. Never included in LLM blocks."""
    docs = {d["id"]: d for d in documents if d["case_id"] == result["case_id"]}
    cache = {}
    candidates = result.get("candidates", []) or result.get("claims", [])
    for item in candidates:
        sources = []
        for e in item["evidence"]:
            doc = docs.get(e["document_id"])
            if not doc:
                continue
            block = next((b for b in doc["blocks"] if b["block_id"] == e["block_id"]), None)
            if block:
                if doc["id"] not in cache:
                    cache[doc["id"]] = pdf_reader(result["case_id"], doc["id"])
                sources.append(source_geometry(cache[doc["id"]], e, block, item.get("raw_value")))
        item["sources"] = sources
    # Reconciled field candidates and all_candidates share references before JSON serialization.
    return result


def viewer_html(content, page_number, sources=(), initial_zoom=100, highlight_tone="neutral"):
    initial_zoom = max(70, min(200, int(initial_zoom)))
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        page = pdf[page_number - 1]
        width, height = page.rect.width, page.rect.height
        png = base64.b64encode(
            page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("png")
        ).decode()
    colors = {
        "neutral": ("#b8c6d5", "#789ab7"),
        "attention": ("#edb1b1", "#dc8585"),
        "approved": ("#a7d5b7", "#70b58a"),
    }
    quote_color, value_color = colors.get(highlight_tone, colors["neutral"])
    rectangles, target_y, target_x = [], None, None
    anchor_source = None
    for source_index, source in enumerate(sources):
        if source["page"] != page_number:
            continue
        for key, color in [("rectangles", quote_color), ("value_rectangles", value_color)]:
            for x0, y0, x1, y1 in source.get(key, []):
                rectangles.append(
                    f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{color}" fill-opacity="0.32" stroke="{color}" stroke-width="1"/>'
                )
                # Keep the primary citation in view. Later context citations
                # (year, currency, company) must not move focus away from it.
                if target_y is None or (
                    source_index == anchor_source and key == "value_rectangles"
                ):
                    target_y = y0
                    target_x = (x0 + x1) / 2
                    anchor_source = source_index
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
    body{{margin:0;font:13px Calibri,'Segoe UI',sans-serif;background:#e5ebeb;color:#173446}}header{{height:50px;box-sizing:border-box;padding:8px 10px;background:#f3f6f5;border-bottom:1px solid #ccd8d8;display:flex;gap:9px;align-items:center;white-space:nowrap}}
    header strong{{font-size:12px;font-weight:600;margin-right:auto}}header label{{display:flex;align-items:center;gap:5px;font-size:11px}}input{{accent-color:#446778;width:65px}}button{{font:11px Calibri,sans-serif;cursor:pointer;color:#244958;background:white;border:1px solid #c4d1d4;border-radius:3px;padding:5px 7px}}button:hover{{background:#e4edef}}button:disabled{{opacity:.45;cursor:default}}button:focus-visible,input:focus-visible{{outline:2px solid #af8c59;outline-offset:2px}}#level{{font-variant-numeric:tabular-nums;min-width:32px;font-size:11px}}
    #viewport{{height:calc(100vh - 50px);overflow:auto;outline-offset:-2px}}svg{{display:block;width:{initial_zoom}%;min-width:{initial_zoom}%;background:white}}
    </style></head><body><header><strong>Σελίδα PDF {page_number}</strong><button id="source" {"disabled" if target_y is None else ""}>Στην παραπομπή</button><label>Zoom <input id="zoom" type="range" min="70" max="200" value="{initial_zoom}"></label><span id="level">{initial_zoom}%</span><button id="fit" title="Προσαρμογή στο πλάτος">Στο πλάτος</button></header>
    <div id="viewport" tabindex="0" role="region" aria-label="Σελίδα PDF — κύλιση με τα βέλη"><svg id="page" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    <image width="{width}" height="{height}" href="data:image/png;base64,{png}"/>{"".join(rectangles)}</svg></div>
    <script>const p=document.getElementById('page'),v=document.getElementById('viewport'),z=document.getElementById('zoom');
    function anchor(){{v.scrollTop=Math.max(0,{target_y or 0}/{height}*p.getBoundingClientRect().height-100);v.scrollLeft=Math.max(0,{target_x or 0}/{width}*p.getBoundingClientRect().width-v.clientWidth*0.65)}}
    z.oninput=()=>{{p.style.width=z.value+'%';p.style.minWidth=z.value+'%';document.getElementById('level').textContent=z.value+'%';anchor()}};
    document.getElementById('source').onclick=anchor;document.getElementById('fit').onclick=()=>{{z.value=100;z.oninput()}};
    new ResizeObserver(anchor).observe(v); requestAnimationFrame(anchor);</script></body></html>'''
