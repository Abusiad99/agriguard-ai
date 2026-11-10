"""PDF rendering for generated agricultural reports (English and Arabic).

Renders the stored structured content — never re-queries data — so the PDF says exactly
what the in-app report says. Arabic is shaped (arabic-reshaper) and put in visual order
(python-bidi) one wrapped line at a time; English knowledge-base text inside an Arabic
report stays left-to-right. Fonts: DejaVu Sans (bundled, covers Latin and Arabic;
license in fonts/LICENSE_DEJAVU).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Callable, List, Optional
from xml.sax.saxutils import escape

from PIL import Image as PILImage, ImageDraw
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.application.reporting.i18n import num, t

FONT_DIR = Path(__file__).resolve().parent / "fonts"
RENDERER_VERSION = "pdf-v10"  # part of the PDF cache key: bump when the layout changes
FONT, FONT_BOLD = "AGSans", "AGSans-Bold"
GREEN, GREEN_DARK, INK, MUTED, LINE = (colors.HexColor("#2D6A4F"), colors.HexColor("#1B4332"), colors.HexColor("#1F2933"),
                                        colors.HexColor("#5B6770"), colors.HexColor("#D9E2DC"))
RISK_COLORS = {"low": "#3f9d5a", "moderate": "#e0a400", "high": "#e46a1f", "critical": "#c62828",
               "insufficient_data": "#9ca3af", "none": "#d1d5db"}
PROV_COLORS = {"model": "#2563eb", "model_measurement": "#0f766e", "model_estimate": "#b45309", "rule": "#475569",
               "sourced_rule": "#4338ca", "knowledge_base": "#15803d", "general_guidance": "#6b7280",
               "user_recorded": "#7c3aed", "observation": "#0e7490", "historical": "#334155",
               "weather_provider": "#0369a1", "llm_summary": "#be185d", "system": "#6b7280"}
PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 3.2 * cm

_registered = False


def _register_fonts() -> None:
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        _registered = True


def _visual(text: str) -> str:
    """Arabic letters shaped and the line put in display order."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


def _has_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" or "ﭐ" <= ch <= "﻿" for ch in text)


class Writer:
    def __init__(self, locale: str):
        _register_fonts()
        self.locale = locale
        self.rtl = locale == "ar"
        align = TA_RIGHT if self.rtl else TA_LEFT
        self.styles = {
            "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=20, leading=26, textColor=GREEN_DARK, alignment=align),
            "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=13.5, leading=18, textColor=GREEN_DARK, alignment=align,
                                 spaceBefore=10, spaceAfter=5),
            "h3": ParagraphStyle("h3", fontName=FONT_BOLD, fontSize=10.5, leading=14, textColor=INK, alignment=align, spaceBefore=4),
            "body": ParagraphStyle("body", fontName=FONT, fontSize=9.5, leading=13.5, textColor=INK, alignment=align),
            "small": ParagraphStyle("small", fontName=FONT, fontSize=7.8, leading=10.5, textColor=MUTED, alignment=align),
            "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.6, leading=11.5, textColor=INK, alignment=align),
            "cellb": ParagraphStyle("cellb", fontName=FONT_BOLD, fontSize=8.6, leading=11.5, textColor=INK, alignment=align),
        }

    def p(self, text: str, style: str = "body", width: float = CONTENT_W, lang: Optional[str] = None, color: Optional[str] = None):
        """Paragraph(s). Arabic text is wrapped in logical order, then each line shaped."""
        text = str(text or "")
        st = self.styles[style]
        # Only text that *is* English (knowledge-base passages) runs left-to-right in an Arabic
        # report; short Latin values (names, codes) stay in the page's right-to-left flow.
        if self.rtl and lang == "en":
            st = ParagraphStyle(f"{style}-ltr", parent=st, alignment=TA_LEFT)
        if color:
            st = ParagraphStyle(f"{style}-c", parent=st, textColor=colors.HexColor(color))
        if not _has_arabic(text):
            return Paragraph(escape(text).replace("\n", "<br/>"), st)
        lines = self._wrap(text, st.fontName, st.fontSize, width)
        return Paragraph("<br/>".join(escape(_visual(line)) for line in lines), st)

    @staticmethod
    def _wrap(text: str, font: str, size: float, width: float) -> List[str]:
        out = []
        for para in text.split("\n"):
            line = ""
            for word in para.split():
                candidate = f"{line} {word}".strip()
                # Narrower than the cell (table padding + margin) so ReportLab never re-wraps a
                # line that is already in visual order (that would swap its words across lines).
                if line and pdfmetrics.stringWidth(_visual(candidate), font, size) > width * 0.96 - 16:
                    out.append(line)
                    line = word
                else:
                    line = candidate
            out.append(line)
        return out

    def row(self, cells: list) -> list:
        return list(reversed(cells)) if self.rtl else cells

    def s(self, text: str) -> str:
        """Single-line string for chart labels."""
        return _visual(text) if _has_arabic(text) else text


def _table(rows, widths, header=False, zebra=True, rtl=False):
    tbl = Table(rows, colWidths=list(reversed(widths)) if rtl else widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF4EE"))]
    if zebra:
        for i in range(1 if header else 0, len(rows), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7FAF8")))
    tbl.setStyle(TableStyle(style))
    return tbl


def _prov_label(w: Writer, prov: dict) -> str:
    """Kind of source; model and rule versions are listed once, under Methods."""
    kind = (prov or {}).get("kind", "system")
    label = t(w.locale, f"prov.{kind}")
    if prov.get("citation"):
        label += f" · {prov['citation']}"
    return label


def _fact_rows(w: Writer, facts: List[dict]) -> list:
    rows = []
    for f in facts:
        value = f.get("display") or "—"
        color = None if f.get("available", True) else "#9a3412"
        value_par = w.p(value, "cell", CONTENT_W * 0.5, lang=f.get("lang"), color=color)
        under = [value_par]
        if f.get("note"):
            under.append(w.p(f["note"], "small", CONTENT_W * 0.5))
        prov = w.p(_prov_label(w, f.get("provenance") or {}), "small", CONTENT_W * 0.22,
                   color=PROV_COLORS.get((f.get("provenance") or {}).get("kind"), "#6b7280"))
        rows.append(w.row([w.p(f.get("label", ""), "cellb", CONTENT_W * 0.28), under, prov]))
    return rows


def _chart(w: Writer, chart: dict) -> Drawing:
    width, height = CONTENT_W, 5.2 * cm
    d = Drawing(width, height)
    xs = [w.s(str(x)) for x in chart["x"]]
    series = [s for s in chart["series"] if any(v is not None for v in s["values"])]
    palette = [colors.HexColor(c) for c in ("#2D6A4F", "#c62828", "#2563eb", "#b45309")]
    if chart["kind"] == "bar":
        c = VerticalBarChart()
        c.data = [[v or 0 for v in s["values"]] for s in series]
        for i in range(len(series)):
            c.bars[i].fillColor = palette[i % len(palette)]
            c.bars[i].strokeColor = None
    else:
        c = HorizontalLineChart()
        c.data = [[v for v in s["values"]] for s in series]
        for i in range(len(series)):
            c.lines[i].strokeColor = palette[i % len(palette)]
            c.lines[i].strokeWidth = 1.6
    c.x, c.y, c.width, c.height = 30, 28, width - 50, height - 50
    c.categoryAxis.categoryNames = xs if len(xs) <= 14 else [x if i % max(1, len(xs) // 10) == 0 else "" for i, x in enumerate(xs)]
    c.categoryAxis.labels.fontName = FONT
    c.categoryAxis.labels.fontSize = 6.5
    c.categoryAxis.labels.angle = 30
    c.categoryAxis.labels.boxAnchor = "ne"
    c.valueAxis.labels.fontName = FONT
    c.valueAxis.labels.fontSize = 7
    d.add(c)
    lx = 30
    for i, s in enumerate(series):
        label = w.s(s["label"])
        d.add(String(lx, height - 10, "■", fontName=FONT, fontSize=8, fillColor=palette[i % len(palette)]))
        d.add(String(lx + 9, height - 10, label, fontName=FONT, fontSize=7.5, fillColor=INK))
        lx += 20 + pdfmetrics.stringWidth(label, FONT, 7.5)
    return d


def region_map_png(cells: List[dict], selected_key: Optional[str], size: int = 640) -> bytes:
    """Grid cells of the report region coloured by the stored risk estimate (or grey when
    there is none). Only aggregated cells — no point locations exist in a report."""
    img = PILImage.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    if not cells:
        return _png(img)
    south = min(c["area"]["bounds"]["south"] for c in cells)
    north = max(c["area"]["bounds"]["north"] for c in cells)
    west = min(c["area"]["bounds"]["west"] for c in cells)
    east = max(c["area"]["bounds"]["east"] for c in cells)
    pad = 40
    scale = (size - 2 * pad) / max(north - south, east - west, 1e-6)

    def xy(lat, lon):
        return pad + (lon - west) * scale, size - pad - (lat - south) * scale

    for c in cells:
        b = c["area"]["bounds"]
        level = (c.get("prediction") or {}).get("risk_level") or "none"
        x0, y0 = xy(b["north"], b["west"])
        x1, y1 = xy(b["south"], b["east"])
        draw.rectangle([x0, y0, x1, y1], fill=RISK_COLORS.get(level, "#d1d5db"), outline="#ffffff", width=2)
        if c.get("positives"):
            r = 6
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#111827")
        if c["area"].get("grid_key") == selected_key:
            draw.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline="#111827", width=4)
    draw.text((pad, size - pad + 10), f"{south:.2f}°, {west:.2f}°", fill="#374151")
    draw.text((size - pad - 90, pad - 25), f"{north:.2f}°, {east:.2f}°", fill="#374151")
    return _png(img)


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image_flowable(path: Path, overlay: Optional[Path], max_w: float, max_h: float) -> Optional[RLImage]:
    try:
        base = PILImage.open(path).convert("RGB")
        if overlay is not None and overlay.is_file():
            ov = PILImage.open(overlay).convert("RGBA").resize(base.size)
            alpha = ov.split()[3].point(lambda a: int(a * 0.6))
            ov.putalpha(alpha)
            base = PILImage.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
        base.thumbnail((1200, 1200))
        buf = io.BytesIO()
        base.save(buf, format="JPEG", quality=88)
        buf.seek(0)
        ratio = min(max_w / base.width, max_h / base.height)
        return RLImage(buf, width=base.width * ratio, height=base.height * ratio)
    except Exception:  # noqa: BLE001 - a missing/corrupt image must not break the report
        return None


def render_report_pdf(report: dict, resolve: Callable[[str], Optional[Path]]) -> bytes:
    """report: the public report dict (content + metadata). resolve: storage key -> local path."""
    c = report["content"]
    w = Writer(report["locale"])
    loc = w.locale
    story: list = []
    ref = report["reference"]

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(GREEN_DARK)
        canvas.rect(0, PAGE_H - 1.0 * cm, PAGE_W, 1.0 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_BOLD, 9)
        brand = t(loc, "brand")
        if w.rtl:
            canvas.drawRightString(PAGE_W - 1.6 * cm, PAGE_H - 0.65 * cm, brand)
            canvas.setFont(FONT, 8)
            canvas.drawString(1.6 * cm, PAGE_H - 0.65 * cm, ref)
        else:
            canvas.drawString(1.6 * cm, PAGE_H - 0.65 * cm, brand)
            canvas.setFont(FONT, 8)
            canvas.drawRightString(PAGE_W - 1.6 * cm, PAGE_H - 0.65 * cm, ref)
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT, 7)
        page = w.s(f"{t(loc, 'chrome.page')} {doc.page}")
        canvas.drawCentredString(PAGE_W / 2, 0.8 * cm, page)
        canvas.restoreState()

    doc = SimpleDocTemplate(io.BytesIO(), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.4 * cm, title=c["title"], author="AgriGuard AI")

    # --- cover
    story += [Spacer(1, 1.2 * cm), w.p(t(loc, "brand"), "h3", color="#2D6A4F"), Spacer(1, 4),
              w.p(t(loc, f"type.{c['type']}"), "h1"), Spacer(1, 6), w.p(c["title"].split(" — ", 1)[-1], "h2"), Spacer(1, 10)]
    meta = [[w.p(t(loc, "chrome.reference"), "cellb"), w.p(ref, "cell")],
            [w.p(t(loc, "chrome.version"), "cellb"), w.p(str(report["version"]), "cell")],
            [w.p(t(loc, "chrome.generated"), "cellb"), w.p(report["generated_display"], "cell")]]
    story.append(_table([w.row(r) for r in meta], [CONTENT_W * 0.3, CONTENT_W * 0.7], rtl=w.rtl))
    status = c.get("status") or {}
    story += [Spacer(1, 10), w.p(f"{status.get('label', '')}", "h2", color="#1B4332")]
    if status.get("qualifier"):
        story.append(w.p(status["qualifier"], "small"))
    if report.get("synthetic"):
        story += [Spacer(1, 6), w.p(t(loc, "chrome.synthetic"), "h3", color="#b45309")]
    story += [Spacer(1, 8), w.p(t(loc, "chrome.disclaimer"), "small")]

    if c.get("chapters"):  # schema v2: the nine chapters of an assessment
        story += _v2_body(w, report, resolve)
        buf = io.BytesIO()
        doc.filename = buf
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
        return buf.getvalue()

    # --- executive summary
    nar = c.get("narrative") or {}
    story += [w.p(t(loc, "chrome.executive_summary"), "h2")]
    for s in nar.get("executive_summary", []):
        story.append(w.p(s["text"], "body"))
        story.append(Spacer(1, 3))
    story.append(w.p(t(loc, "chrome.narrative.llm" if nar.get("source") == "llm" else "chrome.narrative.template"), "small"))

    # --- key facts
    story += [w.p(t(loc, "chrome.key_facts"), "h2"),
              _table(_fact_rows(w, c.get("key_facts", [])), [CONTENT_W * 0.28, CONTENT_W * 0.5, CONTENT_W * 0.22], rtl=w.rtl)]

    media = {m["id"]: m for m in c.get("media", [])}
    charts = {ch["id"]: ch for ch in c.get("charts", [])}

    # --- sections
    for sec in c.get("sections", []):
        block = [w.p(sec["title"], "h2")]
        if sec.get("note"):
            block.append(w.p(sec["note"], "small"))
        if sec.get("text"):
            block.append(w.p(sec["text"], "body"))
        if sec.get("facts"):
            block.append(_table(_fact_rows(w, sec["facts"]), [CONTENT_W * 0.28, CONTENT_W * 0.5, CONTENT_W * 0.22], rtl=w.rtl))
        if sec.get("rows"):
            header = [w.p(cell["label"], "cellb", CONTENT_W / len(sec["rows"][0]["cells"])) for cell in sec["rows"][0]["cells"]]
            body = [[w.p(cell.get("display") or "—", "cell", CONTENT_W / len(r["cells"]), lang=cell.get("lang")) for cell in r["cells"]]
                    for r in sec["rows"][:60]]
            n = len(header)
            block.append(Spacer(1, 4))
            block.append(_table([w.row(header)] + [w.row(r) for r in body], [CONTENT_W / n] * n, header=True, rtl=w.rtl))
        for cid in sec.get("chart_ids", []) or []:
            if cid in charts:
                block += [Spacer(1, 4), _chart(w, charts[cid]),
                          w.p(_prov_label(w, charts[cid].get("provenance") or {}), "small")]
        if sec.get("map") and report.get("region_map_png"):
            img = RLImage(io.BytesIO(report["region_map_png"]), width=9 * cm, height=9 * cm)
            legend = " · ".join(f"{t(loc, 'v.risk.' + k)}" for k in ("low", "moderate", "high", "critical", "none"))
            block += [Spacer(1, 4), img, w.p(legend, "small"), w.p(t(loc, "chrome.prediction_not_observation"), "small")]
        imgs = []
        for mid in sec.get("media_ids", []) or []:
            m = media.get(mid)
            if not m or m.get("overlay_of") or not m.get("storage_key"):
                continue
            path = resolve(m["storage_key"])
            overlay = next((resolve(o["storage_key"]) for o in media.values()
                            if o.get("overlay_of") == mid and o["kind"] == "segmentation_overlay"), None)
            flow = _image_flowable(path, None, CONTENT_W / 2 - 8, 6.5 * cm) if path else None
            if flow:
                imgs.append([flow, w.p(m.get("caption", ""), "small", CONTENT_W / 2 - 8)])
            if overlay and path:
                ov = _image_flowable(path, overlay, CONTENT_W / 2 - 8, 6.5 * cm)
                if ov:
                    imgs.append([ov, w.p(t(loc, "m.segmentation"), "small", CONTENT_W / 2 - 8)])
        for i in range(0, len(imgs), 2):
            pair = imgs[i:i + 2]
            cells = [[p[0], p[1]] for p in pair]
            tbl = Table([w.row([x[0] for x in cells]), w.row([x[1] for x in cells])], colWidths=[CONTENT_W / 2] * len(cells))
            tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            block += [Spacer(1, 4), tbl]
        for ev in sec.get("events", []) or []:
            block.append(w.p(f"{ev['display_date']} — {ev['event'].replace('_', ' ')}", "cell"))
        for h in sec.get("hypotheses", []) or []:
            block.append(w.p(f"• {h['text']}", "body"))
        story.append(KeepTogether(block[:3]) if len(block) > 3 else KeepTogether(block))
        story += block[3:] if len(block) > 3 else []

    # --- recommendations
    story += [Spacer(1, 8), w.p(t(loc, "chrome.recommendations"), "h2")]
    current = None
    for r in c.get("recommendations", []):
        if r["category"] != current:
            current = r["category"]
            story.append(w.p(r["category_label"], "h3", color="#2D6A4F"))
        rows = [[w.p(t(loc, "chrome.priority"), "small"), w.p(r["priority_label"], "cellb")],
                [w.p(t(loc, "chrome.reason"), "small"), w.p(r["reason"], "cell")],
                [w.p(t(loc, "chrome.timing"), "small"), w.p(r["timing"], "cell")],
                [w.p(t(loc, "chrome.objective"), "small"), w.p(r["objective"], "cell")]]
        if r.get("details", {}).get("text"):
            rows.append([w.p(t(loc, "sec.treatment"), "small"),
                         w.p(r["details"]["text"], "cell", CONTENT_W * 0.78, lang=r["details"].get("lang"))])
        if r.get("evidence"):
            rows.append([w.p(t(loc, "chrome.evidence"), "small"),
                         w.p("; ".join(f"{e['label']}: {e['display']}" for e in r["evidence"] if e.get("label")), "cell")])
        if r.get("warnings"):
            rows.append([w.p(t(loc, "chrome.warnings"), "small"), w.p("\n".join(r["warnings"]), "cell", color="#9a3412")])
        rows.append([w.p(t(loc, "chrome.provenance"), "small"), w.p(_prov_label(w, r.get("provenance") or {}), "small")])
        story.append(KeepTogether([w.p(r["title"], "h3"),
                                   _table([w.row(x) for x in rows], [CONTENT_W * 0.22, CONTENT_W * 0.78], zebra=False, rtl=w.rtl),
                                   Spacer(1, 6)]))

    # --- limitations, methods, sources
    story += [w.p(t(loc, "chrome.limitations"), "h2")] + [w.p(f"• {x}", "body") for x in c.get("limitations", [])]
    story.append(w.p(t(loc, "chrome.methods"), "h2"))
    mrows = [w.row([w.p(m["name"], "cellb"), w.p(t(loc, f"prov.{m['kind']}"), "cell"), w.p(str(m.get("version") or "—"), "cell")])
             for m in c.get("methods", [])]
    if mrows:
        story.append(_table(mrows, [CONTENT_W * 0.35, CONTENT_W * 0.3, CONTENT_W * 0.35], rtl=w.rtl))
    story.append(w.p(t(loc, "chrome.sources"), "h2"))
    for src in report.get("sources", [])[:40]:
        story.append(w.p(f"{src.get('kind')}: {src.get('table')}/{src.get('id')}", "small", lang="en"))
    story.append(w.p(f"data hash {report['data_hash'][:16]} · {report['generator_version']} · {report['schema_version']}", "small", lang="en"))

    buf = io.BytesIO()
    doc.filename = buf
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ============================================================================ schema v2
STATEMENT_COLORS = {"measured": "#0f766e", "model": "#2563eb", "estimate": "#b45309", "evaluation": "#1d4ed8",
                    "knowledge": "#15803d", "reference": "#4338ca", "rule": "#475569", "hypothesis": "#a16207",
                    "missing": "#9a3412", "observation": "#0e7490"}
HORIZON_COLORS = {"immediate": "#b91c1c", "short_term": "#b45309", "long_term": "#2D6A4F"}


def _refmark(w: Writer, refs, numbers: dict) -> str:
    ns = sorted({numbers[r] for r in refs or [] if r in numbers})
    if not ns:
        return ""
    sep = "، " if w.rtl else ", "
    return " [" + sep.join(num(n, w.locale, 0) for n in ns) + "]"


def _chart_v2(w: Writer, chart: dict) -> Drawing:
    d = _chart(w, chart)
    markers = chart.get("markers") or []
    if not markers or not chart.get("x"):
        return d
    from reportlab.graphics.shapes import Line

    width, height = CONTENT_W, 5.2 * cm
    x0, plot_w, n = 30, width - 50, len(chart["x"])
    for i, mk in enumerate(markers):
        x = x0 + (mk["index"] + 0.5) * plot_w / max(1, n)
        d.add(Line(x, 28, x, height - 22, strokeColor=colors.HexColor("#7c3aed"), strokeWidth=0.8, strokeDashArray=[2, 2]))
        d.add(String(x + 2, height - 22 - 8 * (i % 3), w.s(mk.get("label", ""))[:40], fontName=FONT, fontSize=5.8,
                     fillColor=colors.HexColor("#7c3aed")))
    return d


def _panel(w: Writer, m: dict, media: dict, resolve, numbers: dict, width: float):
    """One visual result: title, image (overlay composed on its base photo), explanation."""
    key = m.get("storage_key")
    path = resolve(key) if key else None
    base = media.get(m["overlay_of"]) if m.get("overlay_of") else None
    if base is not None:
        base_path = resolve(base["storage_key"]) if base.get("storage_key") else None
        flow = _image_flowable(base_path, path, width - 6, 6.2 * cm) if base_path and path else None
    else:
        flow = _image_flowable(path, None, width - 6, 6.2 * cm) if path else None
    if flow is None:
        return None
    cell = [w.p(m.get("title") or "", "cellb", width), flow]
    if m.get("caption"):
        cell.append(w.p(m["caption"], "small", width))
    if m.get("explanation"):
        cell.append(w.p(m["explanation"] + _refmark(w, m.get("refs"), numbers), "small", width))
    return cell


def _section_v2(w: Writer, sec: dict, media: dict, charts: dict, report: dict, resolve, numbers: dict) -> list:
    loc = w.locale
    block = [w.p(sec["title"], "h3", color="#1B4332")]
    if sec.get("note"):
        block.append(w.p(sec["note"], "small"))
    if sec.get("text"):
        block.append(w.p(sec["text"] + _refmark(w, sec.get("refs"), numbers), "body"))
    for st in sec.get("statements") or []:
        tag = t(loc, f"stk.{st['kind']}")
        block.append(w.p(f"■ {tag}: {st['text']}{_refmark(w, st.get('refs'), numbers)}", "cell",
                         color=STATEMENT_COLORS.get(st["kind"])))
    if sec.get("facts"):
        facts = [dict(f, provenance=dict(f.get("provenance") or {})) for f in sec["facts"]]
        rows = _fact_rows(w, facts)
        for row, f in zip(rows, facts):
            if f.get("refs"):
                prov = w.p(_prov_label(w, f["provenance"]) + _refmark(w, f["refs"], numbers), "small", CONTENT_W * 0.22,
                           color=PROV_COLORS.get(f["provenance"].get("kind"), "#6b7280"))
                row[0 if w.rtl else -1] = prov
        block.append(_table(rows, [CONTENT_W * 0.28, CONTENT_W * 0.5, CONTENT_W * 0.22], rtl=w.rtl))
    if sec.get("rows"):
        cells0 = sec["rows"][0]["cells"]
        n = len(cells0)
        style = "cell" if n <= 6 else "small"
        header = [w.p(cell["label"], "cellb" if n <= 6 else "small", CONTENT_W / n) for cell in cells0]
        body = [[w.p(cell.get("display") or "—", style, CONTENT_W / n, lang=cell.get("lang"),
                     color=None if cell.get("available", True) else "#9a3412") for cell in r["cells"]]
                for r in sec["rows"][:60]]
        block += [Spacer(1, 3), _table([w.row(header)] + [w.row(r) for r in body], [CONTENT_W / n] * n, header=True, rtl=w.rtl)]
    for cid in sec.get("chart_ids") or []:
        if cid in charts:
            ch = charts[cid]
            block += [Spacer(1, 3), w.p(ch.get("title", ""), "small"), _chart_v2(w, ch)]
            if ch.get("note"):
                block.append(w.p(ch["note"], "small"))
            block.append(w.p(_prov_label(w, ch.get("provenance") or {}), "small"))
    if sec.get("map") and report.get("region_map_png"):
        img = RLImage(io.BytesIO(report["region_map_png"]), width=8.5 * cm, height=8.5 * cm)
        legend = " · ".join(t(loc, "v.risk." + k) for k in ("low", "moderate", "high", "critical", "none"))
        m = media.get("region_map") or {}
        block += [Spacer(1, 3), img, w.p(legend, "small"), w.p(m.get("explanation") or "", "small"),
                  w.p(t(loc, "chrome.prediction_not_observation"), "small")]
    panels = []
    for mid in sec.get("media_ids") or []:
        m = media.get(mid)
        if m and m.get("kind") != "region_map":
            p = _panel(w, m, media, resolve, numbers, CONTENT_W / 2 - 6)
            if p:
                panels.append(p)
    for i in range(0, len(panels), 2):
        pair = panels[i:i + 2]
        tbl = Table([w.row(pair)], colWidths=[CONTENT_W / 2] * len(pair))
        tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
        block += [Spacer(1, 3), tbl]
    for item in sec.get("items") or []:
        when = f" — {item['when']}" if item.get("when") else ""
        block.append(w.p(f"• {item['text']}{when}{_refmark(w, item.get('refs'), numbers)}", "cell"))
    for ev in sec.get("events") or []:
        block.append(w.p(f"{ev['display_date']} — {ev.get('label') or ev['event'].replace('_', ' ')}", "cell"))
    for h in sec.get("hypotheses") or []:
        block.append(w.p(f"• {t(loc, 'chrome.hypothesis')}: {h['text']}", "cell", color="#a16207"))
    block.append(Spacer(1, 5))
    return [KeepTogether(block[:4])] + block[4:]


def _recommendations_v2(w: Writer, content: dict, numbers: dict) -> list:
    loc = w.locale
    out, current = [], None
    for r in content.get("recommendations", []):
        group_heading = []
        if r.get("horizon") != current:
            current = r.get("horizon")
            group_heading = [w.p(r.get("horizon_label") or current, "h3", color=HORIZON_COLORS.get(current, "#2D6A4F"))]
        rows = [[w.p(t(loc, "chrome.priority"), "small"), w.p(f"{r['priority_label']} · {r['category_label']}", "cellb")],
                [w.p(t(loc, "chrome.reason"), "small"), w.p(r["reason"], "cell")],
                [w.p(t(loc, "chrome.timing"), "small"), w.p(r["timing"], "cell")],
                [w.p(t(loc, "chrome.objective"), "small"), w.p(r["objective"], "cell")]]
        details = r.get("details") or {}
        if details.get("text"):
            rows.append([w.p(t(loc, "sec.treatment"), "small"),
                         w.p(details["text"], "cell", CONTENT_W * 0.78, lang=details.get("lang"))])
        for item in details.get("items") or []:
            rows.append([w.p("•", "small"), w.p(item["text"] + _refmark(w, item.get("refs"), numbers), "cell")])
        if r.get("evidence"):
            rows.append([w.p(t(loc, "chrome.evidence"), "small"),
                         w.p("; ".join(f"{e['label']}: {e['display']}" for e in r["evidence"] if e.get("label")), "cell")])
        if r.get("warnings"):
            rows.append([w.p(t(loc, "chrome.warnings"), "small"), w.p("\n".join(r["warnings"]), "cell", color="#9a3412")])
        rows.append([w.p(t(loc, "chrome.basis"), "small"),
                     w.p((r.get("basis_label") or "") + _refmark(w, r.get("refs"), numbers), "small",
                         color=PROV_COLORS.get((r.get("provenance") or {}).get("kind"), "#475569"))])
        out.append(KeepTogether(group_heading + [w.p(r["title"], "h3"),
                                                 _table([w.row(x) for x in rows], [CONTENT_W * 0.22, CONTENT_W * 0.78],
                                                        zebra=False, rtl=w.rtl),
                                                 Spacer(1, 6)]))
    return out


def _references_v2(w: Writer, content: dict) -> list:
    loc = w.locale
    refs = content.get("references") or []
    if not refs:
        return [w.p(t(loc, "chrome.no_references"), "body")]
    out = [w.p(t(loc, "chrome.references_note"), "small"), Spacer(1, 3)]
    for r in refs:
        head = ". ".join(str(x).rstrip(". ") for x in (r.get("authors"), r.get("title"), r.get("organization"),
                                                        r.get("publication_date")) if x) + "."
        lines = [w.p(f"[{num(r['n'], loc, 0)}] {head}", "cellb", lang="en"),
                 w.p(f"{r.get('source_type_label', '')} · {r['url']}" + (f" · doi:{r['doi']}" if r.get("doi") else ""),
                     "small", lang="en")]
        if r.get("verified_on"):
            lines.append(w.p(f"{t(loc, 'chrome.verified_on')}: {r['verified_on']}", "small"))
        for claim in r.get("claims") or []:
            lines.append(w.p(f"{t(loc, 'chrome.supports')}: {claim}", "small"))
        out.append(KeepTogether(lines + [Spacer(1, 5)]))
    return out


def _v2_body(w: Writer, report: dict, resolve) -> list:
    c = report["content"]
    loc = w.locale
    media = {m["id"]: m for m in c.get("media", [])}
    charts = {ch["id"]: ch for ch in c.get("charts", [])}
    numbers = {r["id"]: r["n"] for r in c.get("references") or []}
    story: list = []
    for i, ch in enumerate(c["chapters"], start=1):
        heading = w.p(f"{num(i, loc, 0)}. {ch['title']}", "h2")
        start = len(story)
        if ch["id"] == "summary":
            nar = c.get("narrative") or {}
            for s in nar.get("executive_summary", []):
                story += [w.p(s["text"], "body"), Spacer(1, 3)]
            story.append(w.p(t(loc, "chrome.narrative.llm" if nar.get("source") == "llm" else "chrome.narrative.template"), "small"))
            story += [Spacer(1, 4), _table(_fact_rows(w, c.get("key_facts", [])),
                                           [CONTENT_W * 0.28, CONTENT_W * 0.5, CONTENT_W * 0.22], rtl=w.rtl)]
        for sec in (s for s in c.get("sections", []) if s.get("chapter") == ch["id"] and s["id"] != "technical"):
            story += _section_v2(w, sec, media, charts, report, resolve, numbers)
        if ch["id"] == "actions":
            story += _recommendations_v2(w, c, numbers)
        if ch["id"] == "limitations":
            missing = c.get("missing") or []
            if missing:
                story.append(w.p(t(loc, "chrome.missing_information"), "h3", color="#1B4332"))
                rows = [w.row([w.p(m.get("label") or "", "cellb", CONTENT_W * 0.35),
                               w.p(m.get("reason") or "", "cell", CONTENT_W * 0.65)]) for m in missing]
                story.append(_table(rows, [CONTENT_W * 0.35, CONTENT_W * 0.65], rtl=w.rtl))
            story.append(w.p(t(loc, "chrome.limitations"), "h3", color="#1B4332"))
            story += [w.p(f"• {x}", "body") for x in c.get("limitations", [])]
        if ch["id"] == "references":
            story += _references_v2(w, c)
            story.append(w.p(t(loc, "chrome.methods"), "h3", color="#1B4332"))
            mrows = [w.row([w.p(m["name"], "cellb"), w.p(t(loc, f"prov.{m['kind']}"), "cell"),
                            w.p(str(m.get("version") or "—"), "cell", lang="en")]) for m in c.get("methods", [])]
            if mrows:
                story.append(_table(mrows, [CONTENT_W * 0.35, CONTENT_W * 0.3, CONTENT_W * 0.35], rtl=w.rtl))
            tech = [f for s in c.get("sections", []) if s["id"] == "technical" for f in s.get("facts", [])]
            if tech:
                story.append(_table(_fact_rows(w, tech), [CONTENT_W * 0.28, CONTENT_W * 0.5, CONTENT_W * 0.22], rtl=w.rtl))
            story.append(w.p(t(loc, "chrome.sources"), "h3", color="#1B4332"))
            for src in report.get("sources", [])[:40]:
                story.append(w.p(f"{src.get('kind')}: {src.get('table')}/{src.get('id')}", "small", lang="en"))
            story.append(w.p(f"data hash {report['data_hash'][:16]} · {report['generator_version']} · {report['schema_version']}",
                             "small", lang="en"))
        # A chapter heading never ends a page on its own: keep it with the chapter's first block.
        # (KeepTogether reports a huge height to force its own split, so it must not be nested.)
        first = story[start:start + 1]
        inner = list(first[0]._content) if first and isinstance(first[0], KeepTogether) else first
        story[start:start + 1] = [KeepTogether([heading] + inner)]
    return story
