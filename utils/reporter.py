from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io

class ReportGenerator:
    @staticmethod
    def generate_pdf_report(hypothesis) -> io.BytesIO:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54
        )
        
        styles = getSampleStyleSheet()
        
        # Define premium typography styles matching the SaaS aesthetic
        title_style = ParagraphStyle(
            name='ReportTitle',
            parent=styles['Title'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#6366f1'), # Indigo accent
            spaceAfter=10
        )
        
        subtitle_style = ParagraphStyle(
            name='ReportSubtitle',
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#9ca3af'), # Cool gray
            spaceAfter=25
        )
        
        h1_style = ParagraphStyle(
            name='ReportH1',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=colors.HexColor('#f3f4f6'), # Off-white text for headers
            backColor=colors.HexColor('#1f2937'), # Dark back bar
            borderPadding=6,
            spaceBefore=15,
            spaceAfter=10,
            keepWithNext=True
        )
        
        body_style = ParagraphStyle(
            name='ReportBody',
            parent=styles['BodyText'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#374151'), # Slate dark
            spaceAfter=8
        )
        
        story = []
        
        # Header block
        story.append(Paragraph(f"AUTONOMOUS DISCOVERY PLATFORM", ParagraphStyle(
            name='TopNavLabel', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor('#818cf8'), spaceAfter=5
        )))
        story.append(Paragraph(hypothesis.title, title_style))
        story.append(Paragraph(f"Formulated Hypothesis • Created: {hypothesis.created_at.strftime('%Y-%m-%d %H:%M:%S')} • Investigator: {hypothesis.owner.username}", subtitle_style))
        story.append(Spacer(1, 10))
        
        # Executive Summary
        story.append(Paragraph("EXECUTIVE SUMMARY", h1_style))
        summary_text = hypothesis.summary if hypothesis.summary else "No summary available."
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 5))
        
        # Description
        story.append(Paragraph("DETAILED DESCRIPTION & BACKGROUND", h1_style))
        desc_text = hypothesis.description if hypothesis.description else "No description available."
        # Standardize returns to html breaks for PDF
        desc_formatted = desc_text.replace("\n", "<br/>").replace("\r", "")
        story.append(Paragraph(desc_formatted, body_style))
        story.append(Spacer(1, 5))
        
        # Methodology
        story.append(Paragraph("PROPOSED METHODOLOGY", h1_style))
        meth_text = hypothesis.methodology if hypothesis.methodology else "No methodology available."
        meth_formatted = meth_text.replace("\n", "<br/>").replace("\r", "")
        story.append(Paragraph(meth_formatted, body_style))
        story.append(Spacer(1, 5))
        
        # Expected Outcomes
        story.append(Paragraph("EXPECTED OUTCOMES & EVALUATION", h1_style))
        outcomes_text = hypothesis.expected_outcomes if hypothesis.expected_outcomes else "No expected outcomes available."
        outcomes_formatted = outcomes_text.replace("\n", "<br/>").replace("\r", "")
        story.append(Paragraph(outcomes_formatted, body_style))
        
        # Build Document
        doc.build(story)
        buffer.seek(0)
        return buffer
