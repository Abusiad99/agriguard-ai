"""
PdfReportGenerator — FR-REPORT-1. Builds a downloadable PDF containing the plant
image, the model result and its decision status (confident / uncertain /
inconclusive), candidates, the model-attention visualization (clearly labelled as
such), measured affected area when a segmentation measurement exists, treatment,
prevention, weather summary, model/pipeline version, limitations, and a QR code.

All dynamic text is XML-escaped before being handed to reportlab's Paragraph, which
interprets markup — knowledge-base text containing "<" or "&" previously could break
the report or inject formatting.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from xml.sax.saxutils import escape

import qrcode
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_STATUS_TEXT = {
    "confident": "Confident model prediction (not a confirmed diagnosis)",
    "uncertain": "Uncertain — several conditions are plausible; see candidates",
    "inconclusive": "Inconclusive — the model could not identify the condition reliably",
    "legacy": "Created by an earlier pipeline version (no decision status recorded)",
}


@dataclass
class ReportData:
    diagnosis_id: str
    plant_name: str
    disease_name: str
    disease_description: str
    severity_level: Optional[str]
    confidence_score: float
    affected_area_pct: Optional[float]
    healthy_area_pct: Optional[float]
    organic_treatment: Optional[str]
    chemical_treatment: Optional[str]
    biological_treatment: Optional[str]
    prevention_advice: List[str]
    weather_summary: Optional[str]
    diagnosed_at: datetime
    original_image_path: str
    heatmap_image_path: Optional[str]
    report_verification_url: str
    decision_status: Optional[str] = None
    candidates: List[dict] = field(default_factory=list)
    model_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    severity_basis: Optional[str] = None
    quality_notes: List[str] = field(default_factory=list)
    expert_review_recommended: bool = False
    limitations: List[str] = field(default_factory=list)
    segmentation_overlay_path: Optional[str] = None


def _p(text: object) -> str:
    return escape("" if text is None else str(text))


class PdfReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(name="AgriHeading", fontSize=18, spaceAfter=12,
                                        textColor=colors.HexColor("#1B4332"), fontName="Helvetica-Bold"))
        self.styles.add(ParagraphStyle(name="AgriSubheading", fontSize=13, spaceBefore=10, spaceAfter=6,
                                        textColor=colors.HexColor("#2D6A4F"), fontName="Helvetica-Bold"))
        self.styles.add(ParagraphStyle(name="AgriBody", fontSize=10, leading=14))
        self.styles.add(ParagraphStyle(name="AgriNote", fontSize=8.5, leading=11,
                                        textColor=colors.HexColor("#555555")))

    def _build_qr_image(self, url: str) -> RLImage:
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return RLImage(buf, width=3 * cm, height=3 * cm)

    @staticmethod
    def _image(path: str, max_w: float, max_h: float) -> Optional[RLImage]:
        try:
            with PILImage.open(path) as im:
                w, h = im.size
        except Exception:  # noqa: BLE001 - a missing image must not abort the report
            return None
        scale = min(max_w / w, max_h / h)
        return RLImage(path, width=w * scale, height=h * scale)

    def generate(self, data: ReportData, output_path: str) -> str:
        doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
        s = self.styles
        story = [
            Paragraph("AgriGuard AI — Plant Health Report", s["AgriHeading"]),
            Paragraph(f"Report ID: {_p(data.diagnosis_id)}", s["AgriBody"]),
            Paragraph(f"Date: {_p(data.diagnosed_at.strftime('%Y-%m-%d %H:%M UTC'))}", s["AgriBody"]),
            Spacer(1, 10),
        ]

        images = []
        original = self._image(data.original_image_path, 8 * cm, 8 * cm)
        if original:
            images.append([original, Paragraph("Original photo", s["AgriNote"])])
        if data.heatmap_image_path:
            heat = self._image(data.heatmap_image_path, 8 * cm, 8 * cm)
            if heat:
                images.append([heat, Paragraph(
                    "Model attention (Grad-CAM): regions that most influenced the prediction. "
                    "Not a map of diseased tissue.", s["AgriNote"])])
        if images:
            table = Table([[cell[0] for cell in images], [cell[1] for cell in images]],
                          colWidths=[8.5 * cm] * len(images))
            table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(table)
        if data.segmentation_overlay_path:
            seg = self._image(data.segmentation_overlay_path, 8 * cm, 8 * cm)
            if seg:
                story += [Spacer(1, 6), seg, Paragraph(
                    "Segmentation: leaf (green) and lesion (magenta) regions predicted by the "
                    "segmentation model.", s["AgriNote"])]

        story.append(Paragraph("Result", s["AgriSubheading"]))
        status_text = _STATUS_TEXT.get(data.decision_status or "legacy", data.decision_status or "")
        if data.affected_area_pct is not None:
            area_text = f"{data.affected_area_pct:.1f}% of visible leaf area"
            if data.severity_basis and data.severity_basis.startswith("legacy"):
                area_text += " (legacy estimate from attention map — not a measurement)"
        else:
            area_text = "Not measured (no validated segmentation model)"
        rows = [
            ["Status", Paragraph(_p(status_text), s["AgriBody"])],
            ["Plant", Paragraph(_p(data.plant_name), s["AgriBody"])],
            ["Leading result", Paragraph(_p(data.disease_name), s["AgriBody"])],
            ["Model confidence", f"{data.confidence_score:.1f}% (calibrated model probability)"],
            ["Visible affected area", Paragraph(_p(area_text), s["AgriBody"])],
            ["Severity category", Paragraph(_p(data.severity_level or
                                               "Not assigned — requires a validated crop-specific scale"),
                                            s["AgriBody"])],
        ]
        table = Table(rows, colWidths=[4.5 * cm, 11 * cm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F5E9")),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story += [table, Spacer(1, 8)]

        if data.candidates:
            story.append(Paragraph("Model candidates", s["AgriSubheading"]))
            cand_rows = [["Candidate", "Probability", "Cause type"]]
            for c in data.candidates[:5]:
                cand_rows.append([Paragraph(_p(c.get("display") or c.get("label")), s["AgriBody"]),
                                  f"{float(c.get('probability_pct') or 0):.1f}%", _p(c.get("cause_type") or "")])
            ct = Table(cand_rows, colWidths=[9 * cm, 3 * cm, 3.5 * cm])
            ct.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F5E9"))]))
            story.append(ct)

        if data.expert_review_recommended:
            story += [Spacer(1, 6), Paragraph(
                "<b>Expert review recommended.</b> Confirm with a local agricultural extension officer or "
                "plant pathologist before applying treatments.", s["AgriBody"])]

        if data.quality_notes:
            story.append(Paragraph("Photo quality notes", s["AgriSubheading"]))
            for note in data.quality_notes:
                story.append(Paragraph(f"• {_p(note)}", s["AgriBody"]))

        story.append(Paragraph("Description", s["AgriSubheading"]))
        story.append(Paragraph(_p(data.disease_description), s["AgriBody"]))

        for title, text in (("Organic treatment", data.organic_treatment),
                            ("Chemical treatment", data.chemical_treatment),
                            ("Biological treatment", data.biological_treatment)):
            if text:
                story.append(Paragraph(title, s["AgriSubheading"]))
                story.append(Paragraph(_p(text), s["AgriBody"]))

        if data.prevention_advice:
            story.append(Paragraph("Prevention advice", s["AgriSubheading"]))
            for tip in data.prevention_advice:
                story.append(Paragraph(f"• {_p(tip)}", s["AgriBody"]))

        if data.weather_summary:
            story.append(Paragraph("Weather at time of scan", s["AgriSubheading"]))
            story.append(Paragraph(_p(data.weather_summary), s["AgriBody"]))
            story.append(Paragraph("Weather is context only; it is never evidence that a plant has a disease.",
                                   s["AgriNote"]))

        story.append(Paragraph("Limitations", s["AgriSubheading"]))
        for item in (data.limitations or [
            "This is an automated image-based assessment, not a laboratory or field diagnosis.",
        ]):
            story.append(Paragraph(f"• {_p(item)}", s["AgriNote"]))
        if data.model_version:
            story.append(Paragraph(f"Model {_p(data.model_version)} · pipeline {_p(data.pipeline_version)}",
                                   s["AgriNote"]))

        story += [Spacer(1, 14), Paragraph("Scan to open this report in AgriGuard (sign-in required):",
                                           s["AgriBody"]), self._build_qr_image(data.report_verification_url)]
        doc.build(story)
        return output_path
