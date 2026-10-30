"""Generate the binary documents of the demo corpus (the PDF and the Word document).

The rest of samples/corpus is plain text and is edited by hand. Acme Payments is a fictional
payments company; its documents agree with each other, so evaluation questions have real
answers. The PDF repeats a header and a footer on every page, as real contracts do, which is
what the strip_boilerplate cleaning rule removes. Run from apps/api:

    uv run --group samples python ../../scripts/samples/generate.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import docx
from docx.shared import Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parents[2] / "samples" / "corpus" / "developer-docs"
STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("Body", parent=STYLES["BodyText"], fontSize=10.5, leading=15, spaceAfter=6)
H1 = ParagraphStyle("H1", parent=STYLES["Heading1"], fontSize=18, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=STYLES["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=6)


def _bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(text, BODY), leftIndent=12) for text in items],
        bulletType="bullet",
        start="\N{BULLET}",
        leftIndent=14,
    )


def _table(rows: list[list[str]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf4")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5cbd8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _page_furniture(canvas: Any, doc: Any) -> None:
    """The header and footer every page of a real contract carries."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#5b6478"))
    width, height = A4
    canvas.drawString(18 * mm, height - 12 * mm, "Acme Payments, Inc. Service Level Agreement")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Confidential. Page {doc.page} of 3")
    canvas.restoreState()


def service_level_agreement() -> None:
    story: list[Any] = [
        Paragraph("Service Level Agreement", H1),
        Paragraph(
            "This Service Level Agreement (SLA) describes the availability Acme Payments, Inc. "
            "commits to for the Acme Payments API and the service credits customers receive "
            "when that commitment is missed. It applies to customers on the Growth and "
            "Enterprise plans.",
            BODY,
        ),
        Paragraph("1. Service commitment", H2),
        Paragraph(
            "Acme Payments will use commercially reasonable efforts to make the Payments API "
            "available with a Monthly Uptime Percentage of at least 99.95% in each calendar "
            "month. Availability is measured by synthetic requests sent every minute from three "
            "regions to api.acme-payments.example.",
            BODY,
        ),
        Paragraph("2. Definitions", H2),
        Paragraph(
            "A minute counts as downtime when more than 5% of valid requests in that minute fail "
            "with a server error. The Monthly Uptime Percentage is the total number of minutes "
            "in the month minus the minutes of downtime, divided by the total number of minutes "
            "in the month.",
            BODY,
        ),
        Paragraph("3. Service credits", H2),
        Paragraph(
            "If the Monthly Uptime Percentage falls below the commitment, the customer is "
            "eligible for a service credit, calculated as a percentage of the monthly platform "
            "fees for the affected month:",
            BODY,
        ),
        _table(
            [
                ["Monthly Uptime Percentage", "Service credit"],
                ["Below 99.95% but at least 99.0%", "10% of monthly fees"],
                ["Below 99.0% but at least 95.0%", "25% of monthly fees"],
                ["Below 95.0%", "50% of monthly fees"],
            ],
            [80 * mm, 60 * mm],
        ),
        Paragraph(
            "Service credits are the customer's sole remedy for unavailability. The total credit "
            "for a month never exceeds 50% of the monthly fees for that month.",
            BODY,
        ),
        PageBreak(),
        Paragraph("4. Claiming a credit", H2),
        Paragraph(
            "To claim a service credit, contact support within 30 days of the end of the month in "
            "which the downtime occurred. Include the request ids and timestamps of failed "
            "requests. Approved credits are applied to the next invoice and cannot be exchanged "
            "for cash.",
            BODY,
        ),
        Paragraph("5. Exclusions", H2),
        Paragraph("The commitment does not apply to unavailability caused by:", BODY),
        _bullets(
            [
                "Scheduled maintenance announced at least 48 hours in advance, up to 4 hours per "
                "month.",
                "Events outside our reasonable control, such as natural disasters.",
                "The customer's own systems, network or misuse of the API.",
                "Features labelled beta or preview, and test mode.",
            ]
        ),
        Paragraph("6. Support response times", H2),
        Paragraph(
            "Severity 1 means payments cannot be processed. Severity 2 means a feature is "
            "degraded but payments succeed. First response targets by plan:",
            BODY,
        ),
        _table(
            [
                ["Severity", "Enterprise", "Growth"],
                ["Severity 1", "15 minutes, 24/7", "1 hour, 24/7"],
                ["Severity 2", "1 hour", "4 business hours"],
                ["Severity 3", "4 business hours", "1 business day"],
            ],
            [45 * mm, 50 * mm, 50 * mm],
        ),
        PageBreak(),
        Paragraph("7. Incident communication", H2),
        Paragraph(
            "During a major incident Acme Payments posts updates on status.acme-payments.example "
            "at least every 30 minutes until the incident is resolved. A written post-incident "
            "report is published within 5 business days of resolution.",
            BODY,
        ),
        Paragraph("8. Changes to this SLA", H2),
        Paragraph(
            "Acme Payments may update this SLA with at least 90 days' notice. Changes never reduce "
            "the commitment during a customer's current subscription term.",
            BODY,
        ),
    ]
    path = OUT / "Service Level Agreement.pdf"
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title="Service Level Agreement",
        author="Acme Payments, Inc.",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
    )
    doc.build(story, onFirstPage=_page_furniture, onLaterPages=_page_furniture)


def security_overview() -> None:
    d = docx.Document()
    d.core_properties.title = "Security and Compliance Overview"
    d.core_properties.author = "Acme Payments, Inc."
    style = d.styles["Normal"]
    style.font.size = Pt(10.5)

    def heading(text: str, level: int) -> None:
        d.add_heading(text, level=level)

    def paragraph(text: str) -> None:
        d.add_paragraph(text)

    def bullets(items: list[str]) -> None:
        for item in items:
            d.add_paragraph(item, style="List Bullet")

    heading("Security and Compliance Overview", 0)
    paragraph(
        "This overview explains how Acme Payments protects payment data and which "
        "certifications and reports are available to customers and their auditors."
    )
    heading("Certifications", 1)
    paragraph(
        "Acme Payments is certified as a PCI DSS Level 1 Service Provider, the highest level of "
        "assessment in the payments industry. The assessment is performed every year by an "
        "independent Qualified Security Assessor. A SOC 2 Type II report covering security, "
        "availability and confidentiality is available under a non-disclosure agreement."
    )
    heading("Encryption", 1)
    paragraph(
        "All traffic to the API and the dashboard is encrypted with TLS 1.2 or higher. Data at "
        "rest is encrypted with AES-256. Card numbers are tokenized as soon as they reach us and "
        "stored in a separate card vault, isolated from the rest of the platform, so your "
        "systems never need to handle raw card numbers."
    )
    heading("Data residency and retention", 1)
    paragraph(
        "Customer data is stored in the United States by default. Customers in the European "
        "Union can request that their data is stored in the Frankfurt region."
    )
    paragraph(
        "Transaction records are retained for 7 years to meet financial regulations. Request "
        "logs are retained for 90 days. When an account is closed, personal data that is not "
        "subject to a legal retention requirement is deleted within 30 days."
    )
    heading("Access control", 1)
    bullets(
        [
            "Dashboard users with the admin role must use two-factor authentication.",
            "Employee access to production systems requires hardware security keys and is "
            "reviewed every quarter.",
            "Support staff can only view customer data after the customer grants temporary "
            "access from the dashboard.",
        ]
    )
    heading("Testing and vulnerability management", 1)
    paragraph(
        "An independent firm performs a penetration test of the platform every year, and a "
        "public bug bounty program rewards researchers who report vulnerabilities."
    )
    heading("Reporting a vulnerability", 1)
    paragraph(
        "Report security issues to security@acme-payments.example. We acknowledge reports within "
        "2 business days and keep the reporter informed until the issue is fixed."
    )
    d.save(OUT / "Security and Compliance Overview.docx")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    service_level_agreement()
    security_overview()
    print(f"wrote 2 documents to {OUT}")


if __name__ == "__main__":
    main()
