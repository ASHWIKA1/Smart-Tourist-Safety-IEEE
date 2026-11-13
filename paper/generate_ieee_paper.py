"""Generate IEEE Conference figures, Word (.docx), and PDF from measured results."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "experiments" / "results"
PAPER_DIR = Path(__file__).resolve().parent
FIG_DIR = PAPER_DIR / "figures"


def generate_figures(p1: dict, p2: dict) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Serif"

    # --- Figure 1: Implemented System Architecture ---
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=300)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    boxes = [
        (0.2, 3.3, 2.2, 1.4, "Module 1: Tourist App\n(Kotlin + Compose)",
         "Registration / Login\nConsent-Gated GPS\nDID Wallet & SOS", "#eff6ff", "#1d4ed8"),
        (3.1, 3.1, 2.6, 1.8, "Module 2: FastAPI Backend\n& Spatial Database",
         "JWT + RBAC Endpoints\nPostgreSQL / PostGIS\nWebSocket Broadcaster", "#f0fdf4", "#15803d"),
        (6.5, 3.5, 3.2, 1.3, "Module 3 & 4: Risk Engine\n(Python + scikit-learn)",
         "Haversine + Polygon Geo-Fence\nIsolation Forest + Hybrid Fusion", "#fefce8", "#a16207"),
        (6.5, 1.4, 3.2, 1.4, "Module 5: Blockchain Identity\n(Ed25519 + SHA-256)",
         "Off-Chain VC Storage\nHyperledger Fabric / Ledger\nHash, Expiry & Revocation", "#fdf2f8", "#be185d"),
        (3.1, 0.5, 2.6, 1.4, "Module 6: Authority\nDashboard (React)",
         "OpenStreetMap + Zones\nLive Incident Lifecycle\nVC Verifier & Audit", "#f8fafc", "#334155"),
    ]

    for x, y, w, h, title, body, fc, ec in boxes:
        rect = patches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
            linewidth=1.4, edgecolor=ec, facecolor=fc
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h - 0.35, title, ha="center", va="center",
                fontsize=8.2, fontweight="bold", color=ec)
        ax.text(x + w / 2, y + (h - 0.55) / 2, body, ha="center", va="center",
                fontsize=7.0, color="#1e293b")

    arrows = [
        ((2.48, 4.00), (3.02, 4.00), "HTTPS\nGPS/SOS", (0.0, 0.24)),
        ((5.78, 4.15), (6.42, 4.15), "Evaluate", (0.0, 0.18)),
        ((5.78, 3.25), (6.42, 2.35), "Anchor /\nVerify", (-0.06, -0.30)),
        ((4.40, 3.02), (4.40, 1.98), "WebSocket\nAlerts", (0.48, 0.0)),
    ]
    for (x1, y1), (x2, y2), lbl, (dx, dy) in arrows:
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", lw=1.3, color="#334155"),
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + dx, my + dy, lbl, ha="center", va="center", fontsize=6.5, color="#0f172a")

    plt.tight_layout(pad=0.2)
    fig.savefig(FIG_DIR / "fig1_architecture.png", dpi=300)
    plt.close(fig)

    # --- Figure 2: Experiment A Model Comparison ---
    exp_a = p1["experiment_a_model_comparison"]
    labels = ["Rule-Based", "LOF", "Isolation\nForest", "Geo-fence +\nIF (Hybrid)"]
    precision = [r["precision"] for r in exp_a]
    recall = [r["recall"] for r in exp_a]
    f1 = [r["f1_score"] for r in exp_a]

    x = range(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(5.6, 3.2), dpi=300)
    ax.bar([i - width for i in x], precision, width, label="Precision", color="#2563eb")
    ax.bar(x, recall, width, label="Recall", color="#16a34a")
    ax.bar([i + width for i in x], f1, width, label="F1-Score", color="#ea580c")
    ax.set_ylim(0, 1.15)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Score", fontsize=9)
    ax.set_title("Experiment A: Detection Performance (300 Held-Out Trajectories)", fontsize=9.5)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend(fontsize=7.8, loc="lower right")
    for idx, val in enumerate(f1):
        ax.text(idx + width, val + 0.02, f"{val:.2f}", ha="center", fontsize=7)
    plt.tight_layout()
    fig.savefig(FIG_DIR / "fig2_model_comparison.png", dpi=300)
    plt.close(fig)

    # --- Figure 3: Experiment B GPS Error Sensitivity ---
    exp_b = p1["experiment_b_gps_sensitivity"]
    conds = ["2m\nErr", "5m\nErr", "10m\nErr", "15m\nErr", "30%\nDropout", "15%\nJumps"]
    f1_b = [r["f1_score"] for r in exp_b]
    fah_b = [r["false_alerts_per_hour"] for r in exp_b]

    fig, ax1 = plt.subplots(figsize=(5.8, 3.2), dpi=300)
    ax2 = ax1.twinx()
    bars = ax1.bar(conds, f1_b, width=0.48, color="#0284c7", alpha=0.85, label="F1-Score")
    line = ax2.plot(conds, fah_b, color="#dc2626", marker="o", linewidth=1.8, label="False Alerts/hr")
    ax1.set_ylim(0, 1.15)
    ax2.set_ylim(0, 35)
    ax1.set_ylabel("F1-Score", fontsize=9, color="#0369a1")
    ax2.set_ylabel("False Alerts / Tourist-Hour", fontsize=9, color="#b91c1c")
    ax1.tick_params(axis="x", labelsize=8)
    ax1.set_title("Experiment B: GPS Noise, Dropout, and Jump Sensitivity", fontsize=9.5)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=7.8, loc="upper left")
    plt.tight_layout()
    fig.savefig(FIG_DIR / "fig3_gps_sensitivity.png", dpi=300)
    plt.close(fig)


# --- Word XML Helpers for IEEE Conference Two-Column Format ---

def _set_cell_margins(cell, top=40, bottom=40, left=70, right=70):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for m, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = OxmlElement(f"w:{m}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def _set_cell_borders(cell, top=None, bottom=None, left="none", right="none"):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        el = OxmlElement(f"w:{side}")
        if val in (None, "none"):
            el.set(qn("w:val"), "none")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(val))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
        tcBorders.append(el)
    tcPr.append(tcBorders)


def _set_two_columns(section, col_count=2, space_inches=0.25):
    sectPr = section._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sectPr.append(cols)
    cols.set(qn("w:num"), str(col_count))
    cols.set(qn("w:space"), str(int(space_inches * 1440)))
    cols.set(qn("w:equalWidth"), "1")


def _configure_page(section):
    section.page_width = Inches(8.5)
    section.page_height = Inches(11.0)
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.95)
    section.left_margin = Inches(0.625)
    section.right_margin = Inches(0.625)


def _add_page_number_header(section):
    section.different_first_page_header_footer = True
    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r1 = p.add_run("SMART TOURIST SAFETY MONITORING AND INCIDENT RESPONSE SYSTEM   |   ")
    r1.font.name = "Times New Roman"
    r1.font.size = Pt(8)
    r1.font.italic = True

    fldSimple = OxmlElement("w:fldSimple")
    fldSimple.set(qn("w:instr"), "PAGE")
    r_pg = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Times New Roman")
    rFonts.set(qn("w:hAnsi"), "Times New Roman")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "16")
    rPr.append(rFonts)
    rPr.append(sz)
    r_pg.append(rPr)
    fldSimple.append(r_pg)
    p._p.append(fldSimple)


def _add_heading_ieee(doc: Document, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text.upper())
    r.font.name = "Times New Roman"
    r.font.size = Pt(10)
    r.font.bold = True
    return p


def _add_sub_heading_ieee(doc: Document, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(10)
    r.font.italic = True
    r.font.bold = True
    return p


def _add_body(doc: Document, text: str, first_line_indent: float = 0.16):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3.5)
    p.paragraph_format.line_spacing = 1.05
    if first_line_indent:
        p.paragraph_format.first_line_indent = Inches(first_line_indent)
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(9.5)
    return p


def _add_equation(doc: Document, eq_text: str, eq_num: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(f"{eq_text}    ({eq_num})")
    r.font.name = "Times New Roman"
    r.font.size = Pt(9)
    r.font.italic = True


def _add_ieee_table(doc: Document, title_num: str, caption: str, headers: list[str], rows: list[list[str]]):
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(6)
    cap.paragraph_format.space_after = Pt(2)
    cap.paragraph_format.keep_with_next = True
    rc1 = cap.add_run(f"TABLE {title_num}\n")
    rc1.font.name = "Times New Roman"
    rc1.font.size = Pt(8.5)
    rc1.font.bold = True
    rc2 = cap.add_run(caption.upper())
    rc2.font.name = "Times New Roman"
    rc2.font.size = Pt(8)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    # Repeat header row if table ever wraps, and keep header attached to first body row
    hdr_trPr = table.rows[0]._tr.get_or_add_trPr()
    hdr_trPr.append(OxmlElement("w:tblHeader"))
    hdr_trPr.append(OxmlElement("w:cantSplit"))

    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_cell_margins(cell, top=30, bottom=30, left=45, right=45)
        _set_cell_borders(cell, top=8, bottom=6, left="none", right="none")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(h)
        r.font.name = "Times New Roman"
        r.font.size = Pt(8)
        r.font.bold = True

    for i, row_vals in enumerate(rows):
        is_last = i == len(rows) - 1
        row_trPr = table.rows[i + 1]._tr.get_or_add_trPr()
        row_trPr.append(OxmlElement("w:cantSplit"))
        for j, val in enumerate(row_vals):
            cell = table.rows[i + 1].cells[j]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_margins(cell, top=24, bottom=24, left=45, right=45)
            _set_cell_borders(cell, top=None, bottom=8 if is_last else None, left="none", right="none")
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            if not is_last:
                p.paragraph_format.keep_with_next = True
            r = p.add_run(val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(7.8)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(3)


def _add_figure(doc: Document, img_path: Path, width_in: float, caption: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(img_path), width=Inches(width_in))

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(0)
    cap.paragraph_format.space_after = Pt(5)
    r = cap.add_run(caption)
    r.font.name = "Times New Roman"
    r.font.size = Pt(8)


def build_ieee_docx(p1: dict, p2: dict, p3: dict) -> Path:
    doc = Document()

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style.font.size = Pt(9.5)

    sec1 = doc.sections[0]
    _configure_page(sec1)
    _add_page_number_header(sec1)

    # Title (single-column top banner)
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tp.paragraph_format.space_before = Pt(0)
    tp.paragraph_format.space_after = Pt(8)
    tr = tp.add_run(
        "Smart Tourist Safety Monitoring and Incident Response System Using AI, "
        "Geo-Fencing, and Blockchain-Based Digital Identity"
    )
    tr.font.name = "Times New Roman"
    tr.font.size = Pt(21)
    tr.font.bold = True

    # Authors 3-column table (borderless)
    auth_table = doc.add_table(rows=1, cols=3)
    auth_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    authors = [
        (
            "Ajay K",
            "Department of Computer Science and Engineering\n"
            "K. S. Rangasamy College of Technology (Autonomous)\n"
            "Tiruchengode, Tamil Nadu, India\n"
            "ajaykannan176@gmail.com",
        ),
        (
            "Ashwika K",
            "Department of Computer Science and Engineering\n"
            "K. S. Rangasamy College of Technology (Autonomous)\n"
            "Tiruchengode, Tamil Nadu, India\n"
            "ashwikakuppusamy@gmail.com",
        ),
        (
            "Dr. B. G. Geetha",
            "Professor, Department of Computer Science and Engineering\n"
            "K. S. Rangasamy College of Technology (Autonomous)\n"
            "Tiruchengode, Tamil Nadu, India\n"
            "geetha@ksrct.ac.in",
        ),
    ]
    for idx, (name, affil) in enumerate(authors):
        cell = auth_table.rows[0].cells[idx]
        _set_cell_borders(cell, top=None, bottom=None, left="none", right="none")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        rn = p.add_run(name + "\n")
        rn.font.name = "Times New Roman"
        rn.font.size = Pt(10.5)
        rn.font.bold = True
        ra = p.add_run(affil)
        ra.font.name = "Times New Roman"
        ra.font.size = Pt(8.5)

    # Continuous section break into 2-column body
    sec2 = doc.add_section(WD_SECTION.CONTINUOUS)
    _configure_page(sec2)
    _set_two_columns(sec2, col_count=2, space_inches=0.25)

    # Abstract
    ap = doc.add_paragraph()
    ap.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ap.paragraph_format.space_before = Pt(4)
    ap.paragraph_format.space_after = Pt(4)
    ap.paragraph_format.line_spacing = 1.05
    ra1 = ap.add_run("Abstract—")
    ra1.font.name = "Times New Roman"
    ra1.font.size = Pt(9)
    ra1.font.bold = True
    ra1.font.italic = True
    ra2 = ap.add_run(
        "Tourists travelling in unfamiliar regions face safety risks including accidents, medical emergencies, "
        "route disorientation, and restricted-area hazards. Fragmented identity checks, location monitoring, "
        "and emergency reporting delay responder situational awareness. This paper presents the six-module "
        "implementation and controlled evaluation of a Smart Tourist Safety Monitoring and Incident Response "
        "System combining Ed25519-signed Verifiable Credentials anchored on a local hash-chained permissioned "
        "ledger (with companion Hyperledger Fabric chaincode), Haversine and polygonal geo-fencing, movement "
        "anomaly detection, a Kotlin Android tourist application, a FastAPI backend with PostGIS spatial schema "
        "and WebSocket streaming, and a React/OpenStreetMap authority dashboard. Personal data remain off-chain "
        "while SHA-256 credential hashes, Ed25519 issuer keys, expiry, and revocation metadata are recorded "
        "on-chain. Trajectory-split simulation tests (Experiments A, B, and feature ablation across 10 seeds) "
        "are separated from implemented software benchmarks (Experiments C and D). Across 10 independent seeds "
        "(300 held-out trajectories per seed at 3.5 m GPS noise), Local Outlier Factor (LOF) and Isolation Forest "
        "achieved F1-scores of 0.9956 ± 0.0032 and 0.9677 ± 0.0110 (0.09 and 0.66 false alerts/tourist-hour), "
        "compared with 0.5108 ± 0.0267 for a static rule baseline and 0.9672 ± 0.0117 for hybrid geo-fencing + "
        "Isolation Forest. Under 10–15 m GPS noise and sudden jumps, false alerts rose sharply, identifying "
        "pre-filtering needs. Implemented identity verification rejected 100% of tampered, expired, revoked, "
        "rogue-signed, and replayed credentials in under 0.45 ms, and live FastAPI-to-WebSocket incident "
        "delivery averaged 137.37 ms across 20 end-to-end workflows."
    )
    ra2.font.name = "Times New Roman"
    ra2.font.size = Pt(9)
    ra2.font.bold = True

    # Index Terms
    ip = doc.add_paragraph()
    ip.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ip.paragraph_format.space_before = Pt(0)
    ip.paragraph_format.space_after = Pt(6)
    ri1 = ip.add_run("Index Terms—")
    ri1.font.name = "Times New Roman"
    ri1.font.size = Pt(9)
    ri1.font.bold = True
    ri1.font.italic = True
    ri2 = ip.add_run(
        "Tourist safety, geo-fencing, blockchain, decentralised identifier, verifiable credentials, "
        "Isolation Forest, anomaly detection, FastAPI, incident response."
    )
    ri2.font.name = "Times New Roman"
    ri2.font.size = Pt(9)
    ri2.font.italic = True

    # I. INTRODUCTION
    _add_heading_ieee(doc, "I. Introduction")
    _add_body(
        doc,
        "Tourism exposes visitors to unfamiliar terrain, language barriers, and localized hazards where "
        "timely emergency coordination is critical [1], [2]. Conventional safety mechanisms—including help desks, "
        "patrols, helplines, and basic SOS apps—typically rely on the tourist recognizing danger, retaining "
        "device connectivity, and manually supplying identity and location details. Simultaneously, paper-based "
        "identity verification is slow and susceptible to loss or forgery, while centralized storage of "
        "passport and personal records increases privacy exposure."
    )
    _add_body(
        doc,
        "Extending our Phase-I architectural design, this paper reports the complete implementation and "
        "empirical validation of a six-module Smart Tourist Safety Monitoring and Incident Response System. "
        "The system links four core capabilities in an end-to-end operational pipeline: (i) privacy-conscious "
        "digital identity using Ed25519-signed Verifiable Credentials (VCs) whose SHA-256 hashes and revocation "
        "states are anchored on a permissioned ledger while personal data stay off-chain; (ii) circular and "
        "polygonal geo-fencing across safe, caution, and restricted zones with warning buffers; (iii) windowed "
        "AI movement-anomaly detection evaluated against rule-based and Local Outlier Factor (LOF) baselines; "
        "and (iv) real-time SOS and incident lifecycle management across a Kotlin Android app, FastAPI backend, "
        "and React/OpenStreetMap authority dashboard."
    )
    _add_body(
        doc,
        "To ensure scientific rigour, we separate simulation-based evaluation from implemented system "
        "measurements. Experiments A, B, and our feature-ablation study evaluate anomaly models and GPS error "
        "sensitivity on synthetic trajectories split strictly by tourist/journey across 10 independent seeds "
        "to prevent window leakage. Experiments C and D measure actual cryptographic verification, tamper/replay "
        "rejection, WebSocket alert delay, and concurrent API throughput on the running software stack. "
        "Consistent with ethical decision-support design, an AI anomaly flag serves as a risk indicator requiring "
        "human review rather than proof of an emergency. Rather than claiming an unprecedented AI-blockchain "
        "paradigm, this work contributes: (1) a reproducible trajectory-split simulation framework; (2) a 10-seed "
        "statistical and feature-ablation comparison of Rule-Based, LOF, Isolation Forest, and hybrid detectors; "
        "(3) GPS noise and jump sensitivity profiling; (4) an empirical analysis showing why zone fusion trades "
        "minor boundary recall for explicit restricted-zone escalation; and (5) a privacy-conscious Ed25519 + "
        "SHA-256 credential-integrity prototype integrated across six working modules."
    )

    # II. RELATED WORK
    _add_heading_ieee(doc, "II. Related Work")
    _add_body(
        doc,
        "Prior tourist-safety research highlights the role of disaster-purpose mobile applications and "
        "GPS/GSM SOS reporting, noting that adoption and communication availability remain critical factors "
        "[1], [2]. Macro-scale tourism risk studies apply interpretable machine learning and deep learning to "
        "produce regional hazard maps and urban crime-hotspot dashboards [3]–[7]. While valuable for strategic "
        "planning, regional risk scores do not evaluate whether an individual tourist's live trajectory is "
        "abnormal."
    )
    _add_body(
        doc,
        "Data-driven geo-fencing provides interpretable boundary checks [8], whereas trajectory outlier surveys "
        "and edge-IoT anomaly frameworks motivate unsupervised detectors such as Isolation Forest [9]–[11]. "
        "Separately, self-sovereign identity (SSI) and Hyperledger Fabric research demonstrate how decentralised "
        "identifiers (DIDs) and off-chain data hashing protect privacy while preserving integrity [12]–[21]. "
        "As summarized in Table I, existing strands are typically studied in isolation; this work integrates "
        "and measures all six modules within a unified prototype."
    )

    _add_ieee_table(
        doc,
        "I",
        "Comparison of Related Research Strands",
        ["Research Strand", "Technology", "Main Focus", "Gap Addressed Here"],
        [
            ["Tourist safety apps [1], [2]", "Mobile / GPS / SOS", "Manual reporting & tracking", "Adds AI fusion & DID"],
            ["Tourism risk models [5]–[7]", "ML / spatial risk", "Regional / urban risk maps", "Per-tourist live incidents"],
            ["Geo-fencing [8]", "Zone boundaries", "Point-vs-boundary alerts", "Warning buffers + AI context"],
            ["Trajectory anomaly [9]–[11]", "LOF / Isolation Forest", "Outlier movement windows", "Trajectory-split & GPS stress"],
            ["SSI & blockchain [12]–[21]", "DID / VC / Fabric", "Off-chain PII + hash anchor", "Ed25519 + revocation + replay"],
            ["Implemented system (Ours)", "Kotlin + FastAPI + React", "6-module integrated platform", "Measured Exp. A–D validation"],
        ],
    )

    # III. SYSTEM ARCHITECTURE
    _add_heading_ieee(doc, "III. System Architecture and Implemented Modules")
    _add_figure(
        doc,
        FIG_DIR / "fig1_architecture.png",
        3.4,
        "Fig. 1. Implemented six-module architecture connecting the Kotlin Android app, FastAPI/PostGIS backend, "
        "geo-fence & AI risk engine, blockchain identity module, and React/OpenStreetMap authority dashboard.",
    )

    _add_sub_heading_ieee(doc, "A. Module 1: Tourist Android Application")
    _add_body(
        doc,
        "Developed in Kotlin using Jetpack Compose (minSdk 26, compileSdk 36), the mobile client supports "
        "tourist registration and JWT login, DID/VC wallet inspection, consent-gated GPS sharing (via "
        "Android LocationManager with explicit ACCESS_FINE_LOCATION runtime permission), live safety status "
        "badges (safe, caution, alert), emergency contact dialing (Intent.ACTION_DIAL), and a high-visibility "
        "SOS button dispatching critical incidents to the backend."
    )

    _add_sub_heading_ieee(doc, "B. Module 2: FastAPI Backend and Spatial Database")
    _add_body(
        doc,
        "The REST and WebSocket backend is built with Python 3.10, FastAPI, and SQLAlchemy 2.0, paired with "
        "a PostgreSQL + PostGIS schema (GEOGRAPHY columns and GIST spatial indexes) for production deployment "
        "and a zero-configuration SQLite mode for local testing. Role-based access control (RBAC) enforces "
        "separation between tourist, authority, and admin JWT principals, hashes passwords via PBKDF2-HMAC-SHA256, "
        "and rejects telemetry if tracking consent is disabled."
    )

    _add_sub_heading_ieee(doc, "C. Module 3 & 4: Geo-Fencing and AI Risk Engine")
    _add_body(
        doc,
        "The geo-fencing engine evaluates circular and polygonal safe, caution, and restricted zones, computes "
        "distance to boundaries and warning buffers, and logs stateful enter/exit transitions. Concurrently, "
        "the AI module extracts a seven-dimensional feature vector from recent GPS windows and runs Isolation "
        "Forest, LOF, rule-based, and context-aware hybrid detectors."
    )

    _add_sub_heading_ieee(doc, "D. Module 5: Blockchain-Based Digital Identity")
    _add_body(
        doc,
        "Personal credential fields remain off-chain in credentials_offchain. An authorized authority issues "
        "a canonical JSON VC signed with Ed25519 and anchors only the DID, credential ID, SHA-256 content hash, "
        "issuer DID, expiry timestamp, and revocation flag onto a hash-chained permissioned ledger. A matching "
        "Hyperledger Fabric smart contract (TouristIdentityContract, fabric-contract-api) mirrors the same "
        "RegisterTrustedIssuer, AnchorCredential, RevokeCredential, and VerifyCredentialAnchor methods."
    )

    _add_sub_heading_ieee(doc, "E. Module 6: Authority Monitoring Dashboard")
    _add_body(
        doc,
        "Built with React 18, TypeScript, Vite, and Leaflet over OpenStreetMap tiles, the authority web "
        "console receives real-time incidents over WebSockets (/ws/authority/alerts), displays safe/caution/"
        "restricted zones and priority-coded markers, supports dynamic zone creation, manages incident status "
        "transitions (pending, acknowledged, in_progress, resolved), and includes a live VC verifier and "
        "ledger block inspector."
    )

    # IV. METHODOLOGY
    _add_heading_ieee(doc, "IV. Methodology and Algorithmic Workflow")
    _add_sub_heading_ieee(doc, "A. Digital Credential Integrity and Security")
    _add_body(
        doc,
        "Given canonical JSON credential body C, the issuer computes SHA-256 hash h = H(C) and Ed25519 "
        "signature sigma = Sign_sk(C). At verification, presented credential C' is canonicalized and accepted "
        "only if h' = H(C') equals the ledger-anchored hash h, sigma verifies under the registered trusted "
        "issuer public key, the current time precedes expiration_date, the ledger revocation flag is false, "
        "and the presentation nonce has not been seen previously (preventing replay attacks):"
    )
    _add_equation(doc, "h = SHA-256(C),  Verify(C') = [H(C') = h] ∧ SigValid ∧ Trusted ∧ ¬Expired ∧ ¬Revoked ∧ ¬Replayed", "1")
    _add_body(
        doc,
        "Because hash anchoring alone cannot prove issuer authenticity, bind a credential to its holder, or "
        "prevent key misuse, our design pairs hash anchoring with trusted-issuer registration, ledger revocation "
        "flags, and one-time presentation nonces. Production deployment additionally requires hardware-backed "
        "holder key binding (e.g., Android Keystore challenge-response) and per-credential random salts inside "
        "C so repeated verifications cannot be correlated across checkpoints via static on-chain hashes. "
        "Experiment C evaluates this logic on our local hash-chained ledger; multi-node Hyperledger Fabric Raft "
        "consensus latency remains unmeasured."
    )

    _add_sub_heading_ieee(doc, "B. Geo-Fence Distance Evaluation")
    _add_body(
        doc,
        "For circular zones centred at (φ₁, λ₁) with radius r and buffer b, distance d from tourist "
        "position (φ₂, λ₂) is computed via the Haversine formula (mean Earth radius R = 6,371,000 m):"
    )
    _add_equation(doc, "a = sin²(Δφ / 2) + cos φ₁ · cos φ₂ · sin²(Δλ / 2)", "2")
    _add_equation(doc, "d = 2R · atan2(√a, √(1 − a))", "3")
    _add_body(
        doc,
        "A position is classified as inside when d ≤ r, in the warning buffer when r < d ≤ r + b, and "
        "outside otherwise. Polygonal zones use ray-casting point-in-polygon combined with local tangent-plane "
        "point-to-segment distance for warning buffers."
    )

    _add_sub_heading_ieee(doc, "C. Movement Feature Extraction and Hybrid Anomaly Detection")
    _add_body(
        doc,
        "Low-accuracy GPS points (> 50 m) are filtered. From consecutive valid observations, we compute "
        "instantaneous speed vᵢ = d(pᵢ₋₁, pᵢ) / (tᵢ − tᵢ₋₁), accumulated stop duration (displacement "
        "< 3 m or speed < 0.35 m/s), mean/max/std speed, mean and max perpendicular distance to the planned "
        "route polyline, and missing-interval gap ratio:"
    )
    _add_equation(doc, "vᵢ = d(pᵢ₋₁, pᵢ) / (tᵢ − tᵢ₋₁),   a(x) = −score_samples(x)", "4")
    _add_equation(doc, "Anomaly(x) = 1 if a(x) ≥ τ, else 0", "5")
    _add_body(
        doc,
        "Threshold tau for Isolation Forest and LOF is calibrated via 120-point grid search on the validation "
        "split to maximize F1-score, whereas the Rule-Based baseline uses fixed domain thresholds (stop ≥ 65 s "
        "with dev ≥ 35 m, max_dev ≥ 95 m, max_speed ≥ 4.8 m/s, or gap_ratio ≥ 0.5). The Hybrid Geo-fencing + "
        "Isolation Forest detector elevates scores inside restricted zones, adds a sensitivity boost (+0.06) in "
        "caution zones and restricted buffers, and applies a mild dampening margin (-0.04) inside safe zones "
        "to curb sightseeing stop false positives. Alert prioritization follows: (1) manual SOS (critical), "
        "(2) restricted-zone entry (high), and (3) AI movement anomaly (warning)."
    )

    # V. EXPERIMENTAL SETUP
    _add_heading_ieee(doc, "V. Experimental Setup and Evaluation Metrics")
    _add_body(
        doc,
        "All experiments were executed locally on Python 3.10.6 (scikit-learn 1.7.2, cryptography 50.0.2, "
        "FastAPI 0.162.5) with fixed random seeds and automated pytest verification (14/14 unit and integration "
        "tests passing, plus Android Gradle debug build and unit tests passing)."
    )
    _add_body(
        doc,
        "1) Simulation Protocol (Experiments A, B & Ablation): Synthetic trajectories (24 points at 5 s "
        "intervals, 120 s each) represent normal walking (50%), safe-zone sightseeing pauses (25%), off-route "
        "stops (10%), erratic speed bursts (8%), and restricted-zone entries (7%). Independent seeds partition "
        "400 training trajectories (normal windows used for unsupervised fitting), 150 validation trajectories "
        "(threshold calibration), and 300 held-out test trajectories at 3.5 m GPS noise—ensuring zero "
        "trajectory leakage. We repeat Experiment A and the feature-ablation study across 10 independent random "
        "seeds and report mean ± 95% confidence intervals. False alerts per simulated tourist-hour are computed "
        "as FA/hr = FP / ((N_normal × 120 s) / 3600). Experiment B tests 200 trajectories per condition across "
        "2 m, 5 m, 10 m, and 15 m Gaussian GPS noise, 30% random packet dropout, and 15% sudden GPS jump "
        "spikes (60–110 m). Results from synthetic scenarios validate algorithmic behaviour under those "
        "assumptions and do not substitute for field tourist trials."
    )
    _add_body(
        doc,
        "2) Implemented System Protocol (Experiments C & D): Experiment C executes 100 end-to-end cryptographic "
        "issuance and verification trials per security condition (valid, modified, expired, revoked, rogue "
        "issuer signature, and replayed nonce). Experiment D runs 20 live HTTP + WebSocket incident cycles "
        "against a running Uvicorn/FastAPI server and measures concurrent telemetry throughput across 100 "
        "requests at concurrency 10. Evaluation metrics follow standard precision, recall, F1-score, FPR, ROC "
        "AUC, false alerts per simulated tourist-hour, detection delay, and API/WebSocket latency."
    )

    # VI. RESULTS AND DISCUSSION
    _add_heading_ieee(doc, "VI. Results and Discussion")
    _add_sub_heading_ieee(doc, "A. Experiment A — 10-Seed Model Comparison and Feature Ablation (Simulated)")
    ms = p3["multi_seed_model_comparison"]
    rows_a = [
        [
            r["model"].replace("Local Outlier Factor (LOF)", "LOF").replace("Geo-fencing + Isolation Forest", "Geo-fence + IF"),
            f"{r['precision']['mean']:.3f}±{r['precision']['ci95']:.3f}",
            f"{r['recall']['mean']:.3f}±{r['recall']['ci95']:.3f}",
            f"{r['f1_score']['mean']:.3f}±{r['f1_score']['ci95']:.3f}",
            f"{r['false_alerts_per_hour']['mean']:.2f}±{r['false_alerts_per_hour']['ci95']:.2f}",
            f"{r['detection_delay_s']['mean']:.2f}±{r['detection_delay_s']['ci95']:.2f}",
        ]
        for r in ms
    ]
    _add_ieee_table(
        doc,
        "II",
        "Experiment A: 10-Seed Model Comparison (Mean ± 95% CI, 300 Test Trajectories/Seed)",
        ["Model", "Prec.", "Rec.", "F1", "FA/hr", "Delay(s)"],
        rows_a,
    )
    _add_figure(
        doc,
        FIG_DIR / "fig2_model_comparison.png",
        3.35,
        "Fig. 2. Experiment A precision, recall, and F1-score across rule-based, LOF, Isolation Forest, "
        "and hybrid detectors on held-out test trajectories.",
    )
    _add_body(
        doc,
        "As shown in Table II and Fig. 2, static rule thresholds achieved full recall (1.000 ± 0.000) but "
        "suffered 19.55 ± 0.57 false alerts/tourist-hour (F1 = 0.511 ± 0.027) by misclassifying benign "
        "wandering and sightseeing pauses. LOF (F1 = 0.996 ± 0.003, 0.09 ± 0.07 FA/hr) and Isolation Forest "
        "(F1 = 0.968 ± 0.011, 0.66 ± 0.29 FA/hr) sharply reduced false alerts with 5.1–5.5 s mean delay. "
        "LOF slightly outperformed Isolation Forest on compact normal clusters, whereas Isolation Forest offers "
        "O(log n) tree scoring independent of stored training samples. The hybrid Geo-fencing + Isolation "
        "Forest detector scored 0.967 ± 0.012 F1; we do not claim unconditional superiority over standalone "
        "Isolation Forest or LOF, as safe-zone dampening trades minor boundary recall for explicit "
        "restricted-zone escalation."
    )

    abl = p3["feature_ablation"]
    rows_abl = [
        [
            "IF" if r["model"] == "Isolation Forest" else "LOF",
            r["feature_subset"].replace("Route deviation only (2)", "Route dev. (2)").replace("Stop duration only (1)", "Stop duration (1)"),
            f"{r['precision']['mean']:.3f}±{r['precision']['ci95']:.3f}",
            f"{r['recall']['mean']:.3f}±{r['recall']['ci95']:.3f}",
            f"{r['f1_score']['mean']:.3f}±{r['f1_score']['ci95']:.3f}",
            f"{r['false_alerts_per_hour']['mean']:.2f}±{r['false_alerts_per_hour']['ci95']:.2f}",
        ]
        for r in abl
    ]
    _add_ieee_table(
        doc,
        "III",
        "Feature Ablation Across 10 Seeds (Mean ± 95% CI)",
        ["Model", "Features", "Prec.", "Rec.", "F1", "FA/hr"],
        rows_abl,
    )
    _add_body(
        doc,
        "Table III presents the 10-seed feature-ablation results. Stop duration alone performs poorly (IF F1 = "
        "0.456 ± 0.022, 19.63 FA/hr) because benign sightseeing stops also accumulate dwell time. Speed alone "
        "misses stationary off-route incidents (IF recall = 0.580 ± 0.034, F1 = 0.710 ± 0.027). Route "
        "deviation alone is the strongest single cue in planned-route simulations (IF F1 = 0.987 ± 0.009, LOF "
        "F1 = 0.999 ± 0.001), while all seven features preserve near-ceiling accuracy (IF F1 = 0.968, LOF F1 "
        "= 0.996) and remain essential when no planned route is registered or erratic speed bursts occur on-route."
    )

    _add_sub_heading_ieee(doc, "B. Experiment B — GPS Accuracy and Reliability Sensitivity")
    exp_b = p1["experiment_b_gps_sensitivity"]
    rows_b = [
        [
            r["condition"],
            str(r["missed_detections_fn"]),
            str(r["false_alerts_fp"]),
            f"{r['precision']:.4f}",
            f"{r['recall']:.4f}",
            f"{r['f1_score']:.4f}",
            f"{r['false_alerts_per_hour']:.2f}",
        ]
        for r in exp_b
    ]
    _add_ieee_table(
        doc,
        "IV",
        "Experiment B: GPS Error, Dropout, and Jump Sensitivity (200 Trajectories / Condition)",
        ["Condition", "FN", "FP", "Prec.", "Rec.", "F1", "FA/hr"],
        rows_b,
    )
    _add_figure(
        doc,
        FIG_DIR / "fig3_gps_sensitivity.png",
        3.35,
        "Fig. 3. Experiment B sensitivity of F1-score and false alerts/hour to GPS noise, missing readings, "
        "and sudden jump spikes.",
    )
    _add_body(
        doc,
        "Table IV and Fig. 3 demonstrate strong robustness to 30% missing GPS readings (F1 = 0.9910, 0.21 "
        "false alerts/hr) and reasonable stability at 2–5 m noise (F1 = 0.8235–0.8352). However, 10–15 m "
        "noise and 15% sudden GPS jump spikes inflated estimated speeds and route deviations, raising false "
        "alerts to 10.60–29.61 per tourist-hour (F1 dropping to 0.3902–0.5180). This confirms that raw GPS "
        "windows in urban canyons require velocity clamping or Kalman/Hampel smoothing prior to feature extraction."
    )

    _add_sub_heading_ieee(doc, "C. Experiment C — Digital Identity Security (Implemented Ledger)")
    exp_c = p1["experiment_c_identity_security"]
    rows_c = [
        [
            r["test_case"].replace("_", " "),
            str(r["total"]),
            str(r["accepted"]),
            str(r["rejected"]),
            f"{r['avg_latency_ms']:.4f}",
        ]
        for r in exp_c["cases"]
    ]
    _add_ieee_table(
        doc,
        "V",
        f"Experiment C: Digital Identity Security ({exp_c['n_trials']} Trials/Case, Issuance Avg {exp_c['avg_issuance_anchor_latency_ms']} ms)",
        ["Test Case", "Total", "Accepted", "Rejected", "Avg Latency (ms)"],
        rows_c,
    )
    _add_body(
        doc,
        f"Across {exp_c['n_trials']} trials per security scenario (Table V), 100/100 valid credentials were "
        f"accepted in 0.3484 ms on average, while 100/100 modified, expired, revoked, rogue-signed, and "
        f"replayed presentations were rejected in 0.3415–0.4303 ms. Issuance plus hash-chain anchoring "
        f"averaged {exp_c['avg_issuance_anchor_latency_ms']} ms across {exp_c['ledger_block_count']} blocks "
        f"with full hash-chain integrity verified ({exp_c['ledger_chain_intact']})."
    )

    _add_sub_heading_ieee(doc, "D. Experiment D — End-to-End Incident Workflow & API Throughput")
    exp_d = p2["experiment_d"]
    perf = p2["backend_performance"]
    _add_ieee_table(
        doc,
        "VI",
        "Experiment D: Live FastAPI + WebSocket Workflow and Concurrent Throughput",
        ["Measured Metric", "Observed Value"],
        [
            ["Completed live HTTP + WebSocket workflows", str(exp_d["workflows_completed"])],
            ["Avg detection-to-WebSocket alert delay", f"{exp_d['avg_detection_to_ws_alert_ms']} ms"],
            ["P95 detection-to-WebSocket alert delay", f"{exp_d['p95_detection_to_ws_alert_ms']} ms"],
            ["Avg end-to-end resolution cycle time", f"{exp_d['avg_end_to_end_resolve_ms']} ms"],
            ["Concurrent telemetry batch (100 req, 10 workers)", f"{perf['throughput_rps']} req/s"],
            ["Mean / P95 telemetry API response time", f"{perf['mean_api_latency_ms']} / {perf['p95_api_latency_ms']} ms"],
        ],
    )
    _add_body(
        doc,
        "On the implemented FastAPI + WebSocket stack (Table VI), restricted-zone entry detection reached the "
        "authority WebSocket channel in 137.37 ms on average (582.57 ms P95), and full acknowledgement and "
        "resolution completed in 222.05 ms. Under 10 concurrent workers running SQLite and per-request "
        "Isolation Forest scoring on 24-point windows, throughput measured 8.23 req/s (1132.53 ms mean latency), "
        "highlighting the benefit of migrating to PostgreSQL/PostGIS connection pooling and asynchronous "
        "worker queues for multi-thousand-tourist deployments."
    )

    # VII. LIMITATIONS AND FUTURE WORK
    _add_heading_ieee(doc, "VII. Limitations and Future Work")
    _add_body(
        doc,
        "Several limitations remain before field deployment. First, Experiments A and B rely on synthetic "
        "trajectories; real consent-based tourist mobility traces are needed to capture diverse sightseeing "
        "and transit behaviours. Second, Experiment B revealed sensitivity to 10–15 m GPS error and jump "
        "spikes; integrating a Hampel jump filter or Kalman smoother is an immediate next step. Third, "
        "while Hyperledger Fabric chaincode has been authored, Experiment C measured our local permissioned "
        "ledger state machine rather than a multi-peer Raft ordering cluster, where consensus latency will be "
        "higher. Finally, Android field trials are required to measure real battery drain under continuous GPS "
        "and cellular handoffs."
    )

    # VIII. CONCLUSION
    _add_heading_ieee(doc, "VIII. Conclusion")
    _add_body(
        doc,
        "This paper presented the end-to-end implementation and empirical evaluation of a six-module Smart "
        "Tourist Safety Monitoring and Incident Response System uniting Kotlin mobile telemetry, FastAPI/"
        "PostGIS services, geo-fencing, unsupervised movement-anomaly detection, Ed25519 + SHA-256 "
        "permissioned identity anchoring, and a React/OpenStreetMap authority dashboard. All 14 automated "
        "backend/core tests, Android Gradle unit tests and APK assembly, and React production builds pass. "
        "Controlled 10-seed trajectory-split evaluations demonstrate F1-scores of 0.9956 ± 0.0032 (LOF) and "
        "0.9677 ± 0.0110 (Isolation Forest) versus 0.5108 ± 0.0267 for static rules, alongside 100% rejection "
        "across five credential attack vectors on our local ledger and 137.37 ms average live WebSocket alert "
        "delivery."
    )

    # ACKNOWLEDGEMENT
    _add_heading_ieee(doc, "Acknowledgement")
    _add_body(
        doc,
        "The authors thank the Department of Computer Science and Engineering, K. S. Rangasamy College of "
        "Technology (Autonomous), Tiruchengode, Tamil Nadu, India, for providing the academic infrastructure "
        "and research guidance supporting this work.",
        first_line_indent=0.0,
    )

    # REFERENCES
    _add_heading_ieee(doc, "References")
    refs = [
        "[1] G. Aliperti and A. M. Cruz, \"Promoting built-for-disaster-purpose mobile applications: An interdisciplinary literature review to increase their penetration rate among tourists,\" J. Hosp. Tour. Manag., vol. 44, pp. 193–210, 2020.",
        "[2] K. Chiranjeevi et al., \"IoT-based smart tourist safety monitoring system,\" Int. Res. J. Eng. Technol., vol. 13, no. 8, 2026.",
        "[3] B. George, \"Towards safer journeys: Exploring the potential of AI in tourism security,\" Int. J. Saf. Secur. Tour. Hosp., 2024.",
        "[4] P. Premananthan et al., \"Machine learning applications in smart tourism: Overview, research challenges, and the road ahead,\" EAI Endorsed Trans. Tour. Technol. Intell., 2024.",
        "[5] Z. Li et al., \"Tourism risk prediction and influencing factor analysis on the Qinghai–Tibet Plateau based on interpretable machine learning,\" ISPRS Int. J. Geo-Inf., vol. 15, no. 5, Art. no. 220, 2026.",
        "[6] A. K. Josephi and M. Maqsood, \"A smart dashboard framework for urban tourism risk analysis using deep learning and machine learning,\" STAP J. Secur. Risk Manag., vol. 2026, no. 1, pp. 112–129, 2026.",
        "[7] T. C. Hakyemez and B. Badur, \"Enhancing deep learning-based crime hotspot predictions with theory-based environmental risk scores,\" Appl. Spat. Anal. Policy, 2025.",
        "[8] I. Sasaki et al., \"Data-driven geofencing design for point-of-interest notifiers utilizing genetic algorithm,\" ISPRS Int. J. Geo-Inf., vol. 13, no. 6, Art. no. 174, 2024.",
        "[9] A. Belhadi et al., \"Trajectory outlier detection: Algorithms, taxonomies, evaluation, and open challenges,\" ACM Trans. Intell. Syst. Technol., vol. 11, 2020.",
        "[10] V. Chandola, A. Banerjee, and V. Kumar, \"Anomaly detection: A survey,\" ACM Comput. Surv., vol. 41, no. 3, 2009.",
        "[11] A. Ali et al., \"An innovative IoT and edge intelligence framework for monitoring elderly people using anomaly detection on data from non-wearable sensors,\" Sensors, vol. 25, Art. no. 1735, 2025.",
        "[12] C. Mazzocca et al., \"A survey on decentralized identifiers and verifiable credentials,\" IEEE Commun. Surv. Tutor., vol. 27, no. 6, pp. 3641–3671, 2025.",
        "[13] A. Mühle et al., \"A survey on essential components of a self-sovereign identity,\" Comput. Sci. Rev., vol. 30, 2018.",
        "[14] R. Soltani, U. T. Nguyen, and A. An, \"A survey of self-sovereign identity ecosystem,\" arXiv:2111.02003, 2021.",
        "[15] S. Figueroa-Lorenzo, J. Añorga Benito, and S. Arrizabalaga, \"Modbus access control system based on SSI over Hyperledger Fabric blockchain,\" Sensors, vol. 21, Art. no. 5438, 2021.",
        "[16] G. Akhison, \"Towards a universal digital identity: A blockchain-based framework for borderless verification,\" Front. Blockchain, vol. 8, 2025.",
        "[17] S. Khairnar, \"Application of blockchain frameworks for decentralized identity and access management of IoT devices,\" IJACSA, vol. 16, no. 6, 2025.",
        "[18] Y. Mountije, D. Agapito, and C. Ramos, \"Reshaping the future of tourism and hospitality industry through blockchain technology: A systematic literature review,\" Inf. Technol. Tour., vol. 27, pp. 317–343, 2025.",
        "[19] J. F. Prados-Castillo et al., \"A review of blockchain technology adoption in the tourism industry from a sustainability perspective,\" J. Theor. Appl. Electron. Commer. Res., vol. 18, no. 2, pp. 814–830, 2023.",
        "[20] R. L. Rana, N. Adamashvili, and C. Tricase, \"The impact of blockchain technology adoption on tourism industry: A systematic literature review,\" Sustainability, vol. 14, Art. no. 7383, 2022.",
        "[21] G. Zyskind, O. Nathan, and A. Pentland, \"Decentralizing privacy: Using blockchain to protect personal data,\" in Proc. IEEE Secur. Privacy Workshops, 2015.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Inches(0.22)
        p.paragraph_format.first_line_indent = Inches(-0.22)
        r = p.add_run(ref)
        r.font.name = "Times New Roman"
        r.font.size = Pt(8)

    out_docx = PAPER_DIR / "Smart_Tourist_Safety_IEEE_Conference_Revised.docx"
    doc.save(str(out_docx))
    return out_docx


def export_pdf_via_word(docx_path: Path, pdf_path: Path) -> bool:
    try:
        import win32com.client  # type: ignore

        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            doc = word.Documents.Open(str(docx_path.resolve()))
            doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)  # wdFormatPDF = 17
            doc.Close(False)
            return True
        finally:
            word.Quit()
    except Exception as exc:
        print(f"Word COM export failed: {exc}")
        return False


def main() -> None:
    p1 = json.loads((RESULTS_DIR / "phase1_results.json").read_text(encoding="utf-8"))
    p2 = json.loads((RESULTS_DIR / "phase2_results.json").read_text(encoding="utf-8"))
    p3 = json.loads((RESULTS_DIR / "ablation_ci_results.json").read_text(encoding="utf-8"))
    generate_figures(p1, p2)
    docx_path = build_ieee_docx(p1, p2, p3)
    pdf_path = PAPER_DIR / "Smart_Tourist_Safety_IEEE_Conference_Revised.pdf"
    ok = export_pdf_via_word(docx_path, pdf_path)
    print(f"Generated DOCX: {docx_path} (exists={docx_path.exists()})")
    print(f"Generated PDF via Word: {pdf_path} (ok={ok}, exists={pdf_path.exists()})")


if __name__ == "__main__":
    main()
