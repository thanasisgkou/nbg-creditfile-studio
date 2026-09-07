"""Printable Greek bulletin from a frozen snapshot. No inference or remote assets."""

from html import escape
from io import BytesIO
from pathlib import Path
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)
from .bulletin import DRAFT


def fonts() -> None:
    if "Bulletin" in pdfmetrics.getRegisteredFontNames():
        return
    for folder, normal, bold in [
        (Path("C:/Windows/Fonts"), "arial.ttf", "arialbd.ttf"),
        (Path("/usr/share/fonts/truetype/dejavu"), "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ]:
        if (folder / normal).exists():
            pdfmetrics.registerFont(TTFont("Bulletin", str(folder / normal)))
            pdfmetrics.registerFont(TTFont("BulletinBold", str(folder / bold)))
            pdfmetrics.registerFontFamily(
                "Bulletin",
                normal="Bulletin",
                bold="BulletinBold",
                italic="Bulletin",
                boldItalic="BulletinBold",
            )
            return
    raise ValueError("Απαιτείται εγκατεστημένη γραμματοσειρά Arial ή DejaVu Sans με ελληνικά.")


def value_text(row: dict) -> str:
    value = row["value"]
    if value is None:
        return "—"
    if row["key"] == "financial_year":
        return str(value)
    if isinstance(value, (float, int)):
        text = f"{value:,.2f}".translate(str.maketrans({",": ".", ".": ","}))
        if row["key"] == "duration_months":
            return f"{value:g} μήνες"
        return text + (" " + row["unit"] if row.get("unit") else "")
    return str(value)


def source_catalog(report: dict) -> tuple[list[dict], dict]:
    sources = []
    lookup = {}
    all_sources = [s for r in report["fields"] for s in r["sources"]]
    all_sources += [s for e in report["corrections"] for s in e.get("documented_sources", [])]
    all_sources += [s for e in report["resolutions"] for s in e["sources"]]
    # Open discrepancies may involve fields outside the ten-field summary
    # (declared turnover/debt). Their sources must survive PDF export too.
    all_sources += [s for c in report["conflicts"] for s in c.get("evidence", [])]
    for s in all_sources:
        key = (s["document_id"], s["page"], s["quote"])
        if key not in lookup:
            lookup[key] = len(sources) + 1
            sources.append(s)
    return sources, lookup


def render_pdf(report: dict, studio: bool = False) -> bytes:
    fonts()
    out = BytesIO()
    body = ParagraphStyle(
        "body",
        fontName="Bulletin",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#263e48"),
        spaceAfter=7,
    )
    small = ParagraphStyle("small", parent=body, fontSize=7.7, leading=10.5)
    source_style = ParagraphStyle("source", parent=body, fontSize=8, leading=10, spaceAfter=2)
    heading = ParagraphStyle(
        "heading",
        parent=body,
        fontName="BulletinBold",
        fontSize=14,
        leading=19,
        spaceBefore=10,
        spaceAfter=10,
    )
    title = ParagraphStyle("title", parent=heading, fontSize=21, leading=26)
    if studio:
        body.fontSize = 10
        body.leading = 15
        heading.textColor = colors.HexColor("#007578")
        title.fontSize = 27
        title.leading = 33
        title.spaceAfter = 18

    def p(text, style=body):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    def date(text):
        return datetime.fromisoformat(text).strftime("%d/%m/%Y %H:%M UTC")

    def period(text):
        if not text:
            return "—"
        try:
            return "\nέως ".join(
                datetime.fromisoformat(t).strftime("%d/%m/%Y") for t in text.split("/")
            )
        except ValueError:
            return text

    def table(data, widths):
        t = Table(
            [[p(v, small) for v in row] for row in data],
            colWidths=widths,
            repeatRows=1,
            hAlign="LEFT",
        )
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7edf2")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd4da")),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        if studio:
            t.setStyle(
                TableStyle(
                    [
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f1f6f6")],
                        ),
                        ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor("#007578")),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ]
                )
            )
        return t

    sources, lookup = source_catalog(report)

    def refs(items):
        return (
            ", ".join("Π" + str(lookup[(s["document_id"], s["page"], s["quote"])]) for s in items)
            or "Χωρίς τεκμηρίωση"
        )

    story = [
        p("NBG · " + ("ΠΡΟΣΧΕΔΙΟ" if report["draft"] else "ΟΛΟΚΛΗΡΩΜΕΝΗ ΠΡΟΕΤΟΙΜΑΣΙΑ"), small),
        p("Δελτίο προετοιμασίας φακέλου χρηματοδότησης", title),
    ]
    if not studio:
        story += [p("Συνθετικά δεδομένα — μόνο για δοκιμές", heading)]
    if report["draft"]:
        story.append(p(DRAFT, heading))
    if report.get("example_notice"):
        story.append(p(report["example_notice"]))
    story += [
        p(report["company"] or "Επωνυμία: εκκρεμεί τεκμηριωμένη επαλήθευση", heading),
        p(
            f"Φάκελος: {report['case_id']}\nΈκδοση: {report['version']} · Έκδοση στις: {date(report['issued_at'])}\nΚατάσταση: {report['state']}\nΕλεγμένα: {report['reviewed_count']}/10 · Εκκρεμή πεδία: {report['pending_count']}"
        ),
        p("Σύνοψη αιτήματος", heading),
    ]
    request = [
        r
        for r in report["fields"]
        if r["key"] in {"requested_amount", "loan_purpose", "duration_months"} and r["complete"]
    ]
    story += [p(r["label"] + ": " + value_text(r)) for r in request] or [
        p("Δεν υπάρχουν επαρκή ελεγμένα πεδία για σύνοψη αιτήματος.")
    ]
    story += [p(report["identity"])] + ([] if studio else [p(report["disclaimer"])])
    story += [
        PageBreak(),
        p(
            "Ελεγμένα στοιχεία φακέλου" if studio else "Τα δέκα πεδία του συμφωνημένου scope",
            heading,
        ),
        p(
            "Οι τελικές χρηματικές τιμές είναι κανονικοποιημένες σε ευρώ. Τα αποσπάσματα διατηρούν την αρχική κλίμακα των εγγράφων.",
            small,
        ),
    ]
    rows = [["Στοιχείο", "Τελική τιμή", "Έτος / περίοδος", "Έλεγχος", "Πηγές"]]
    for r in report["fields"]:
        status = {
            "accepted": "Αποδοχή",
            "corrected": "Διόρθωση",
            "pending": "Προς έλεγχο",
            "unresolved": "Ανεπίλυτο",
        }.get(r["review_status"], r["review_status"])
        if r["note"]:
            status += "\n" + r["note"]
        rows.append([r["label"], value_text(r), period(r.get("year")), status, refs(r["sources"])])
    story.append(table(rows, [32 * mm, 51 * mm, 32 * mm, 39 * mm, 20 * mm]))
    story += [Spacer(1, 8 * mm), p("Έγγραφα που επεξεργάστηκε η εφαρμογή", heading)]
    story += [
        p(f"{d['name']} · {d['page_count']} σελίδες · {d['type']}") for d in report["documents"]
    ]
    story += [p("Ανοικτές εκκρεμότητες", heading)]
    story += [p(i["label"] + ": " + i["reason"]) for i in report["issues"]] or [
        p("Δεν υπάρχουν ανοικτές εκκρεμότητες εντός του συμφωνημένου scope.")
    ]
    for check in report["conflicts"]:
        if check.get("resolution"):
            continue
        details = check["label"] + ": "
        if check["status"] == "NOT_CHECKED":
            details += "Δεν ολοκληρώθηκε η σύγκριση. " + check["explanation"]
        else:
            numeric = check["check_id"] in {"turnover_match", "debt_match", "accounting_equation"}

            def formatted(v):
                return (
                    value_text(dict(value=v, key="revenue", unit="EUR"))
                    if numeric
                    else str(v if v is not None else "—")
                )

            labels = (
                ("Ενεργητικό", "Υποχρεώσεις + ίδια κεφάλαια")
                if check["check_id"] == "accounting_equation"
                else ("Αίτηση", "Οικονομικές καταστάσεις")
            )
            details += f"{labels[0]}: {formatted(check['left_value'])} / {labels[1]}: {formatted(check['right_value'])}."
            if check.get("absolute_difference") is not None:
                details += " Διαφορά: " + formatted(check["absolute_difference"])
                if check.get("percentage_difference") is not None:
                    details += f" ({check['percentage_difference']:.2f}%)."
        story.append(p(details + "\nΠηγές διασταύρωσης: " + refs(check.get("evidence", []))))
    story += [
        Spacer(1, 5 * mm),
        p("Διορθώσεις και επιλύσεις", heading),
        p(
            "Ιστορικό μεταβολών — χωριστά από τις τελικές τιμές. Δεν περιλαμβάνεται ιστορικό συνομιλίας.",
            small,
        ),
    ]
    for e in report["corrections"]:
        story.append(
            p(
                f"{e['document_type']}.{e['field']} · {date(e['timestamp'])}\nΑρχική πρόταση: {e['original_value']} → Διόρθωση: {e['reviewed_value']}\nΑιτιολογία: {e['reviewer_comment']}\nΠηγές: {refs(e.get('documented_sources', []))}"
            )
        )
    active = {c["resolution"]["timestamp"] for c in report["conflicts"] if c.get("resolution")}
    for e in report["resolutions"]:
        status = (
            "Ισχύει για το στιγμιότυπο"
            if e["timestamp"] in active
            else "Ιστορική επίλυση — δεν ισχύει για τις τρέχουσες τιμές"
        )
        story.append(
            p(
                f"{e['check_id']} · {date(e['timestamp'])}\n{e['reason']}\n{status} · Πηγές: {refs(e['sources'])}"
            )
        )
    if not report["corrections"] and not report["resolutions"]:
        story.append(p("Δεν έχουν καταγραφεί διορθώσεις ή επιλύσεις."))
    story += [p("Παραπομπές στα αποθηκευμένα έγγραφα", heading)]
    for n, s in enumerate(sources, 1):
        story.append(
            KeepTogether(
                [
                    p(f"Π{n} · {s['document_name']} · σελίδα {s['page']}", source_style),
                    p(s["quote"], source_style),
                    Spacer(1, 1 * mm),
                ]
            )
        )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Bulletin", 7)
        canvas.setFillColor(colors.HexColor("#526674"))
        if not studio:
            canvas.drawString(18 * mm, 13 * mm, "Συνθετικά δεδομένα — μόνο για δοκιμές")
        canvas.drawRightString(192 * mm, 13 * mm, f"Έκδοση {report['version']} · Σελίδα {doc.page}")
        if report["draft"]:
            canvas.setFillColor(colors.HexColor("#9d4949"))
            canvas.drawString(18 * mm, 20 * mm, "ΠΡΟΣΧΕΔΙΟ — ΕΚΚΡΕΜΕΙΣ ΕΛΕΓΧΟΙ / ΣΤΟΙΧΕΙΑ")
        canvas.restoreState()

    SimpleDocTemplate(
        out,
        pagesize=(210 * mm, 297 * mm),
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=28 * mm,
        title="Δελτίο προετοιμασίας φακέλου χρηματοδότησης",
        author="NBG — τοπική συνεδρία",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
