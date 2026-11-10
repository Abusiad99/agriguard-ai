"""
PdfReportGenerator — FR-REPORT-1. Builds a downloadable PDF containing the plant
image, plant name, disease name, description, highlighted infection area, severity,
confidence, treatment, prevention, weather summary, diagnosis date, and a QR code
(reportlab for layout, qrcode for the QR image) — BR5: only ever called for a
diagnosis that has completed the full pipeline.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from xml.sax.saxutils import escape

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
    # Spraying conditions from app/application/reporting/weather_guidance.py (English),
    # with the references it cites; None for a healthy prediction.
    spraying_guidance: Optional[dict] = None


class PdfReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(name="AgriHeading", fontSize=18, spaceAfter=12,
                                        textColor=colors.HexColor("#1B4332"), fontName="Helvetica-Bold"))
        self.styles.add(ParagraphStyle(name="AgriSubheading", fontSize=13, spaceBefore=10, spaceAfter=6,
                                        textColor=colors.HexColor("#2D6A4F"), fontName="Helvetica-Bold"))
        self.styles.add(ParagraphStyle(name="AgriBody", fontSize=10, leading=14))

    def _build_qr_image(self, url: str) -> RLImage:
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return RLImage(buf, width=3 * cm, height=3 * cm)

    def generate(self, data: ReportData, output_path: str) -> str:
        doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
        story = []

        story.append(Paragraph("AgriGuard AI — Diagnostic Report", self.styles["AgriHeading"]))
        story.append(Paragraph(f"Diagnosis ID: {data.diagnosis_id}", self.styles["AgriBody"]))
        story.append(Paragraph(f"Date: {data.diagnosed_at.strftime('%Y-%m-%d %H:%M UTC')}", self.styles["AgriBody"]))
        story.append(Spacer(1, 12))

        try:
            story.append(RLImage(data.original_image_path, width=8 * cm, height=8 * cm))
        except Exception:
            pass
        if data.heatmap_image_path:
            try:
                story.append(Spacer(1, 6))
                story.append(Paragraph("Highlighted Disease Region", self.styles["AgriSubheading"]))
                story.append(RLImage(data.heatmap_image_path, width=8 * cm, height=8 * cm))
            except Exception:
                pass

        story.append(Paragraph("Diagnosis Summary", self.styles["AgriSubheading"]))
        summary_table = Table([
            ["Plant", data.plant_name],
            ["Disease / Condition", data.disease_name],
            ["Confidence", f"{data.confidence_score:.1f}%"],
            ["Severity", data.severity_level or "N/A"],
            ["Affected Area", f"{data.affected_area_pct:.1f}%" if data.affected_area_pct is not None else "N/A"],
            ["Healthy Area", f"{data.healthy_area_pct:.1f}%" if data.healthy_area_pct is not None else "N/A"],
        ], colWidths=[5 * cm, 10 * cm])
        summary_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F5E9")),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 10))

        story.append(Paragraph("Description", self.styles["AgriSubheading"]))
        # Paragraph parses ReportLab markup: knowledge-base text is escaped so "&" or "<"
        # (e.g. "copper & sulfur", "pH < 6") prints as written instead of failing the scan.
        story.append(Paragraph(escape(data.disease_description or ""), self.styles["AgriBody"]))

        if data.organic_treatment:
            story.append(Paragraph("Organic Treatment", self.styles["AgriSubheading"]))
            story.append(Paragraph(escape(data.organic_treatment), self.styles["AgriBody"]))
        if data.chemical_treatment:
            story.append(Paragraph("Chemical Treatment", self.styles["AgriSubheading"]))
            story.append(Paragraph(escape(data.chemical_treatment), self.styles["AgriBody"]))
        if data.biological_treatment:
            story.append(Paragraph("Biological Treatment", self.styles["AgriSubheading"]))
            story.append(Paragraph(escape(data.biological_treatment), self.styles["AgriBody"]))

        if data.prevention_advice:
            story.append(Paragraph("Prevention Advice", self.styles["AgriSubheading"]))
            for tip in data.prevention_advice:
                story.append(Paragraph(f"• {escape(tip)}", self.styles["AgriBody"]))

        if data.weather_summary:
            story.append(Paragraph("Weather at Scan Time", self.styles["AgriSubheading"]))
            story.append(Paragraph(escape(data.weather_summary), self.styles["AgriBody"]))

        if data.spraying_guidance:
            g = data.spraying_guidance
            numbers = {r["id"]: r["n"] for r in g.get("references", [])}
            story.append(Paragraph("Spraying Conditions at Scan Time", self.styles["AgriSubheading"]))
            story.append(Paragraph(escape(g["summary"]), self.styles["AgriBody"]))
            for item in g.get("items", []):
                marks = sorted(numbers[r] for r in item.get("refs", []) if r in numbers)
                suffix = f" [{', '.join(str(n) for n in marks)}]" if marks else ""
                story.append(Paragraph(f"• {escape(item['text'])}{suffix}", self.styles["AgriBody"]))
            if g.get("references"):
                story.append(Paragraph("Sources", self.styles["AgriSubheading"]))
                for ref in g["references"]:
                    line = ". ".join(str(x).rstrip(". ") for x in (ref.get("authors"), ref.get("title"),
                                                                   ref.get("organization"), ref.get("publication_date")) if x)
                    story.append(Paragraph(f"[{ref['n']}] {escape(line)}. {escape(ref['url'])}", self.styles["AgriBody"]))

        story.append(Spacer(1, 16))
        story.append(Paragraph("Scan to view this report online:", self.styles["AgriBody"]))
        story.append(self._build_qr_image(data.report_verification_url))

        doc.build(story)
        return output_path
