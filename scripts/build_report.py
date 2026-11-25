#!/usr/bin/env python3
"""Build a styled Excel QA report (or guided execution sheet) from a v2.0 workspace.

Usage:
    python scripts/build_report.py <workspace> [--output report.xlsx] [--allow-incomplete]
    python scripts/build_report.py <workspace> --guided-sheet [--output guided.xlsx]
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
except ImportError as exc:  # pragma: no cover - dependency guidance
    print("openpyxl is required. Install it with: pip install openpyxl", file=sys.stderr)
    print(f"Import error: {exc}", file=sys.stderr)
    raise SystemExit(1)

from qa_common import (
    DEFECT_STATUSES,
    SEVERITIES,
    STATUSES,
    TRIAGE_DISPOSITIONS,
    as_list,
    as_text,
    coverage,
    evidence_text,
    load_workspace,
    oracle_text,
    slugify,
    steps_text,
    validate_workspace,
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

NAVY = "1F3864"
BLUE = "2F5597"
LIGHT_BLUE = "D9E2F3"
ZEBRA = "F2F2F2"
WHITE = "FFFFFF"
BORDER_COLOR = "BFBFBF"

TITLE_FONT = Font(name="Calibri", size=18, bold=True, color=WHITE)
SUBTITLE_FONT = Font(name="Calibri", size=10, color="D9E2F3")
SECTION_FONT = Font(name="Calibri", size=11, bold=True, color=NAVY)
LABEL_FONT = Font(name="Calibri", size=10, bold=True, color=NAVY)
HEADER_FONT = Font(name="Calibri", size=10, bold=True, color=WHITE)
BODY_FONT = Font(name="Calibri", size=10, color="000000")
SMALL_FONT = Font(name="Calibri", size=9, color="404040")

THIN = Side(style="thin", color=BORDER_COLOR)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

STATUS_FILLS = {
    "Pass": PatternFill("solid", fgColor="C6EFCE"),
    "Fail": PatternFill("solid", fgColor="FFC7CE"),
    "Blocked": PatternFill("solid", fgColor="D9D9D9"),
    "Needs Clarification": PatternFill("solid", fgColor="FFEB9C"),
    "Observation": PatternFill("solid", fgColor="DDEBF7"),
    "Not Run": PatternFill("solid", fgColor="EDEDED"),
}

STATUS_FONTS = {
    "Pass": Font(name="Calibri", size=10, bold=True, color="006100"),
    "Fail": Font(name="Calibri", size=10, bold=True, color="9C0006"),
    "Blocked": Font(name="Calibri", size=10, bold=True, color="404040"),
    "Needs Clarification": Font(name="Calibri", size=10, bold=True, color="9C6500"),
    "Observation": Font(name="Calibri", size=10, bold=True, color="1F4E79"),
    "Not Run": Font(name="Calibri", size=10, color="595959"),
}

SEVERITY_FILLS = {
    "Critical": PatternFill("solid", fgColor="C00000"),
    "High": PatternFill("solid", fgColor="FFC7CE"),
    "Medium": PatternFill("solid", fgColor="FFEB9C"),
    "Low": PatternFill("solid", fgColor="DDEBF7"),
    "Enhancement": PatternFill("solid", fgColor="E2EFDA"),
}

SEVERITY_FONTS = {
    "Critical": Font(name="Calibri", size=10, bold=True, color=WHITE),
    "High": Font(name="Calibri", size=10, bold=True, color="9C0006"),
    "Medium": Font(name="Calibri", size=10, bold=True, color="9C6500"),
    "Low": Font(name="Calibri", size=10, bold=True, color="1F4E79"),
    "Enhancement": Font(name="Calibri", size=10, bold=True, color="375623"),
}

SEVERITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Enhancement": 4, "None": 5}
ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def clean(value, limit: int = 32000) -> str:
    text = as_text(value)
    text = ILLEGAL_CHARS.sub("", text)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def write_cell(ws, row: int, column: int, value, *, font=None, fill=None, alignment=None, border=True):
    cell = ws.cell(row=row, column=column)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        cell.value = value
    else:
        text = clean(value)
        cell.value = text
        if isinstance(text, str) and text.startswith(FORMULA_PREFIXES):
            cell.data_type = "s"
    cell.font = font or BODY_FONT
    if fill:
        cell.fill = fill
    cell.alignment = alignment or Alignment(vertical="top", wrap_text=True)
    if border:
        cell.border = BORDER
    return cell


def merge_write(
    ws,
    row: int,
    start_col: int,
    end_col: int,
    value,
    *,
    font=None,
    fill=None,
    alignment=None,
    border: bool = True,
):
    ws.merge_cells(start_row=row, start_column=start_col, end_row=row, end_column=end_col)
    top_left = write_cell(ws, row, start_col, value, font=font, fill=fill, alignment=alignment, border=border)
    for col in range(start_col + 1, end_col + 1):
        sibling = ws.cell(row=row, column=col)
        if fill:
            sibling.fill = fill
        if border:
            sibling.border = BORDER
    return top_left


def estimate_height(values: list, widths: list[int], cap: int = 140, min_height: float = 18) -> float:
    lines = 1
    for index, value in enumerate(values):
        width = widths[index] if index < len(widths) else 20
        text = clean(value)
        if not text:
            continue
        count = 0
        for part in text.split("\n"):
            count += max(1, math.ceil(len(part) / max(width - 2, 8)))
        lines = max(lines, count)
    return min(cap, max(min_height, lines * 14.0))


def section(ws, row: int, title: str, last_col: int = 6) -> int:
    merge_write(
        ws,
        row,
        start_col=1,
        end_col=last_col,
        value=title,
        font=SECTION_FONT,
        fill=PatternFill("solid", fgColor=LIGHT_BLUE),
        alignment=Alignment(vertical="center"),
    )
    ws.row_dimensions[row].height = 22
    return row + 1


def set_widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def write_table(
    ws,
    start_row: int,
    headers: list[str],
    rows: list[list],
    widths: list[int],
    *,
    fill_map: dict[int, dict] | None = None,
    font_map: dict[int, dict] | None = None,
    header_height: int = 34,
) -> int:
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[start_row].height = header_height

    for row_offset, values in enumerate(rows, start=1):
        row = start_row + row_offset
        for col, value in enumerate(values, start=1):
            fill = None
            font = None
            if fill_map and col in fill_map:
                fill = fill_map[col].get(clean(value))
            if font_map and col in font_map:
                font = font_map[col].get(clean(value))
            if fill is None and row_offset % 2 == 0:
                fill = PatternFill("solid", fgColor=ZEBRA)
            write_cell(ws, row, col, value, fill=fill, font=font)
        ws.row_dimensions[row].height = estimate_height(values, widths)

    return start_row + len(rows)


def finish_sheet(ws, last_row: int, last_col: int, freeze: str = "A2") -> None:
    ws.freeze_panes = freeze
    ws.auto_filter.ref = f"A1:{get_column_letter(last_col)}{max(1, last_row)}"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"


def add_list_validation(ws, column_letter: str, values: list[str], last_row: int) -> None:
    validation = DataValidation(
        type="list",
        formula1='"' + ",".join(values) + '"',
        allow_blank=True,
        showDropDown=False,
    )
    validation.error = "Choose a value from the list."
    validation.errorTitle = "Invalid value"
    ws.add_data_validation(validation)
    validation.add(f"{column_letter}2:{column_letter}{max(2, last_row + 200)}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def build_summary(wb: Workbook, loaded: dict, stats: dict, issues: list, *, incomplete: bool) -> None:
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = NAVY
    widths = [28, 18, 18, 22, 18, 18]
    set_widths(ws, widths)

    merge_write(ws, 1, 1, 6, "Blackbox UI QA Report", font=TITLE_FONT, fill=PatternFill("solid", fgColor=NAVY))
    ws.row_dimensions[1].height = 30
    meta = loaded.get("meta") or {}
    subtitle = (
        f"{as_text(meta.get('app')) or 'Application'}  |  "
        f"{as_text(meta.get('environment')) or 'environment unknown'}  |  "
        f"mode: {as_text(meta.get('execution_mode')) or 'browser'}  |  "
        f"generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    merge_write(ws, 2, 1, 6, subtitle, font=SUBTITLE_FONT, fill=PatternFill("solid", fgColor=NAVY))
    ws.row_dimensions[2].height = 20

    row = 3
    if incomplete:
        merge_write(
            ws,
            row,
            1,
            6,
            "DRAFT — validation errors remain. Do not deliver until resolved.",
            font=Font(name="Calibri", size=11, bold=True, color=WHITE),
            fill=PatternFill("solid", fgColor="C00000"),
            alignment=Alignment(vertical="center"),
        )
        ws.row_dimensions[row].height = 22
        row += 2

    row = section(ws, row, "Engagement", 6)
    pairs = [
        ("App", meta.get("app")),
        ("URL", meta.get("url")),
        ("Environment", meta.get("environment")),
        ("Staging confirmed", "Yes" if meta.get("staging_confirmed") is True else "No / unconfirmed"),
        ("Version / build", meta.get("version")),
        ("Scope", meta.get("scope")),
        ("In-scope modules", meta.get("in_scope_modules")),
        ("Depth / Atlas mode", f"{as_text(meta.get('depth'))} / {stats['reconciliation']['atlas_coverage_mode']}"),
        ("Execution mode", as_text(meta.get("execution_mode")) or "browser"),
        ("Roles", meta.get("roles")),
        ("Host / browser", f"{as_text(meta.get('host'))} / {as_text(meta.get('browser_tool'))}"),
        ("Viewports", meta.get("viewports")),
        ("Locale", meta.get("locale")),
        ("Started / Finished", f"{as_text(meta.get('started_at'))} -> {as_text(meta.get('finished_at')) or 'in progress'}"),
    ]
    for index in range(0, len(pairs), 2):
        left = pairs[index]
        write_cell(ws, row, 1, left[0], font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
        merge_write(ws, row, 2, 3, left[1])
        h_left = estimate_height([left[0], left[1]], [widths[0], widths[1] + widths[2]])
        h_right = 18.0
        if index + 1 < len(pairs):
            right = pairs[index + 1]
            write_cell(ws, row, 4, right[0], font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
            merge_write(ws, row, 5, 6, right[1])
            h_right = estimate_height([right[0], right[1]], [widths[3], widths[4] + widths[5]])
        ws.row_dimensions[row].height = max(h_left, h_right)
        row += 1

    run_contract = meta.get("run_contract") if isinstance(meta.get("run_contract"), dict) else {}
    if run_contract:
        row += 1
        row = section(ws, row, "Run contract", 6)
        time_anchor = run_contract.get("time_anchor") if isinstance(run_contract.get("time_anchor"), dict) else {}
        contract_rows = [
            ("Authorized origins", as_text(run_contract.get("authorized_origins"))),
            ("Allowed actions", as_text(run_contract.get("allowed_actions"))),
            ("Forbidden actions", as_text(run_contract.get("forbidden_actions"))),
            ("Direct-URL AuthZ checks", "Yes" if run_contract.get("direct_url_authz_checks", True) else "No"),
            ("Mutation budget", run_contract.get("mutation_budget")),
            ("Data classification", run_contract.get("data_classification")),
            ("Evidence retention", run_contract.get("evidence_retention")),
            (
                "Time anchor",
                f"clock {as_text(time_anchor.get('clock')) or 'not recorded'} | "
                f"user {as_text(time_anchor.get('user_timezone')) or 'not recorded'} | "
                f"tenant {as_text(time_anchor.get('tenant_timezone')) or 'not recorded'} | "
                f"freeze: {'yes' if time_anchor.get('can_freeze_time') is True else 'no'}",
            ),
            ("End state", run_contract.get("end_state")),
        ]
        merged_width = sum(widths[1:6])
        for label, value in contract_rows:
            write_cell(ws, row, 1, label, font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
            merge_write(ws, row, 2, 6, value)
            ws.row_dimensions[row].height = estimate_height([label, value], [widths[0], merged_width])
            row += 1

    row += 1
    row = section(ws, row, "Results & defect breakdown", 6)
    status_header_row = row
    headers_res = [(1, "Test Status"), (2, "Count"), (3, "Defect Status"), (4, "Count"), (5, "Severity"), (6, "Defects")]
    for col, title in headers_res:
        cell = ws.cell(row=row, column=col, value=title)
        cell.font = HEADER_FONT
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.row_dimensions[row].height = 24

    status_counts = stats["status_counts"]
    defect_status_counts = stats["defect_status_counts"]
    severity_counts = stats["severity_counts"]
    sev_list = ["Critical", "High", "Medium", "Low", "Enhancement"]
    max_res_rows = max(len(STATUSES), len(DEFECT_STATUSES), len(sev_list) + 1)

    for offset in range(1, max_res_rows + 1):
        r = status_header_row + offset
        if offset <= len(STATUSES):
            st = STATUSES[offset - 1]
            write_cell(ws, r, 1, st, font=STATUS_FONTS.get(st, BODY_FONT), fill=STATUS_FILLS.get(st))
            write_cell(ws, r, 2, status_counts.get(st, 0), alignment=Alignment(horizontal="center", vertical="center"))
        elif offset == len(STATUSES) + 1:
            write_cell(ws, r, 1, "Total cases", font=Font(name="Calibri", size=10, bold=True))
            write_cell(
                ws,
                r,
                2,
                stats["cases_total"],
                font=Font(name="Calibri", size=10, bold=True),
                alignment=Alignment(horizontal="center", vertical="center"),
            )

        if offset <= len(DEFECT_STATUSES):
            dst = DEFECT_STATUSES[offset - 1]
            write_cell(ws, r, 3, dst)
            write_cell(ws, r, 4, defect_status_counts.get(dst, 0), alignment=Alignment(horizontal="center", vertical="center"))

        if offset <= len(sev_list):
            sev = sev_list[offset - 1]
            write_cell(ws, r, 5, sev, font=SEVERITY_FONTS.get(sev, BODY_FONT), fill=SEVERITY_FILLS.get(sev))
            write_cell(ws, r, 6, severity_counts.get(sev, 0), alignment=Alignment(horizontal="center", vertical="center"))
        elif offset == len(sev_list) + 1:
            write_cell(ws, r, 5, "Pass rate", font=Font(name="Calibri", size=10, bold=True))
            write_cell(
                ws,
                r,
                6,
                f"{stats['pass_rate']:.1f}%",
                font=Font(name="Calibri", size=10, bold=True),
                alignment=Alignment(horizontal="center", vertical="center"),
            )
        ws.row_dimensions[r].height = 20

    row = status_header_row + max_res_rows + 2

    # Place charts side-by-side inside columns A:F so print_area captures them cleanly.
    status_chart = BarChart()
    status_chart.type = "col"
    status_chart.style = 10
    status_chart.title = "Test status"
    status_chart.y_axis.title = "Cases"
    status_chart.height = 6.5
    status_chart.width = 11.0
    data = Reference(ws, min_col=2, min_row=status_header_row, max_row=status_header_row + len(STATUSES))
    cats = Reference(ws, min_col=1, min_row=status_header_row + 1, max_row=status_header_row + len(STATUSES))
    status_chart.add_data(data, titles_from_data=True)
    status_chart.set_categories(cats)
    status_chart.legend = None
    ws.add_chart(status_chart, f"A{row}")

    severity_chart = BarChart()
    severity_chart.type = "col"
    severity_chart.style = 10
    severity_chart.title = "Defects by severity"
    severity_chart.y_axis.title = "Defects"
    severity_chart.height = 6.5
    severity_chart.width = 11.0
    data = Reference(ws, min_col=6, min_row=status_header_row, max_row=status_header_row + len(sev_list))
    cats = Reference(ws, min_col=5, min_row=status_header_row + 1, max_row=status_header_row + len(sev_list))
    severity_chart.add_data(data, titles_from_data=True)
    severity_chart.set_categories(cats)
    severity_chart.legend = None
    ws.add_chart(severity_chart, f"D{row}")

    row += 15

    row = section(ws, row, "Coverage & open questions", 6)
    cov_pairs = [
        ("Controls inventoried", stats["controls_total"], "Relationships mapped", stats["relationships_total"]),
        ("Controls executed (Pass/Fail)", stats["controls_executed"], "Relationships executed", stats["relationships_executed"]),
        ("Controls linked (all)", stats["controls_tested"], "Relationships linked (all)", stats["relationships_verified"]),
        ("Executed control coverage", f"{stats['controls_coverage_pct']:.1f}%", "Executed relationship coverage", f"{stats['relationships_coverage_pct']:.1f}%"),
        ("Total test cases", stats["cases_total"], "Total defects", len(loaded.get("defects") or [])),
        ("Open questions / items", stats["open_questions_count"], "Total question log entries", len(loaded.get("questions") or [])),
    ]
    for l_label, l_val, r_label, r_val in cov_pairs:
        write_cell(ws, row, 1, l_label, font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
        merge_write(ws, row, 2, 3, l_val)
        write_cell(ws, row, 4, r_label, font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
        merge_write(ws, row, 5, 6, r_val)
        ws.row_dimensions[row].height = 20
        row += 1

    row += 1
    row = section(ws, row, "Reconciliation", 6)
    rec = stats["reconciliation"]
    checks = [
        (
            f"Controls ({rec['atlas_coverage_mode']})",
            f"{rec['controls_total']} total | {rec['controls_executed']} executed | {rec['controls_tested']} linked | {rec['controls_unexplained']} unexplained",
            rec["controls_unexplained"] == 0,
        ),
        (
            "Relationships",
            f"{rec['relationships_total']} = {rec['relationships_verified']} linked + {rec['relationships_not_tested']} skipped; {rec['relationships_unexplained']} unexplained",
            rec["relationships_unexplained"] == 0,
        ),
        (
            "Cases",
            f"{rec['cases_total']} = {rec['status_total']} status-counted; {rec['cases_unaccounted']} unaccounted",
            rec["cases_unaccounted"] == 0,
        ),
        (
            "Passes",
            f"{rec['passes_total']} = {rec['passes_with_evidence']} evidenced + {rec['passes_without_evidence']} missing",
            rec["passes_without_evidence"] == 0,
        ),
        (
            "Fails",
            f"{rec['fails_total']} = {rec['fails_with_defect']} linked + {rec['fails_without_defect']} unlinked; {rec['fails_without_triage']} untriaged",
            rec["fails_without_defect"] == 0 and rec["fails_without_triage"] == 0,
        ),
        (
            "Defects",
            f"{rec['defects_total']} = {rec['defects_with_cases']} linked + {rec['defects_without_cases']} orphan",
            rec["defects_without_cases"] == 0,
        ),
        (
            "Skips",
            f"{rec['skips_without_reason']} Blocked/Not Run without a reason",
            rec["skips_without_reason"] == 0,
        ),
        (
            "In-scope modules",
            f"{rec['in_scope_modules_total']} total; {rec['in_scope_modules_without_cases']} without cases",
            rec["in_scope_modules_without_cases"] == 0,
        ),
        (
            "Configuration matrix",
            f"{rec['config_matrix_total']} entries; {rec['config_matrix_unexplained']} unexplained",
            rec["config_matrix_unexplained"] == 0,
        ),
    ]
    for label, detail, ok in checks:
        write_cell(ws, row, 1, label, font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
        merge_write(ws, row, 2, 5, detail)
        status_cell = write_cell(
            ws,
            row,
            6,
            "OK" if ok else "CHECK",
            font=Font(name="Calibri", size=10, bold=True, color="006100" if ok else "9C0006"),
            fill=PatternFill("solid", fgColor="C6EFCE" if ok else "FFC7CE"),
            alignment=Alignment(horizontal="center", vertical="center"),
        )
        ws.row_dimensions[row].height = estimate_height([label, detail], [widths[0], sum(widths[1:5])])
        row += 1

    row += 1
    row = section(ws, row, "Anomaly triage", 6)
    for disposition in TRIAGE_DISPOSITIONS:
        write_cell(ws, row, 1, disposition, font=LABEL_FONT, fill=PatternFill("solid", fgColor=LIGHT_BLUE))
        write_cell(
            ws,
            row,
            2,
            stats["triage_counts"].get(disposition, 0),
            alignment=Alignment(horizontal="center", vertical="center"),
        )
        merge_write(
            ws,
            row,
            3,
            6,
            "Only Defect becomes Fail." if disposition == "Defect" else "",
            font=SMALL_FONT,
        )
        ws.row_dimensions[row].height = 19
        row += 1

    row += 1
    row = section(ws, row, "Top risks / defects", 6)
    defects = sorted(
        loaded.get("defects") or [],
        key=lambda d: (SEVERITY_RANK.get(as_text(d.get("severity")), 9), as_text(d.get("id"))),
    )
    if defects:
        for defect in defects[:5]:
            write_cell(ws, row, 1, as_text(defect.get("id")))
            severity = as_text(defect.get("severity"))
            write_cell(
                ws,
                row,
                2,
                severity,
                font=SEVERITY_FONTS.get(severity, BODY_FONT),
                fill=SEVERITY_FILLS.get(severity),
            )
            title = defect.get("title")
            merge_write(ws, row, 3, 6, title)
            ws.row_dimensions[row].height = estimate_height([title], [sum(widths[2:6])])
            row += 1
    else:
        merge_write(ws, row, 1, 6, "No defects recorded.")
        ws.row_dimensions[row].height = 19
        row += 1

    row += 1
    row = section(ws, row, "Limitations, assumptions and warnings", 6)
    notes = []
    for limitation in as_list(meta.get("limitations")):
        notes.append(f"Limitation: {as_text(limitation)}")
    for question in loaded.get("questions") or []:
        qtype = as_text(question.get("type"))
        qstatus = as_text(question.get("status")) or "Open"
        if qtype in ("Limitation", "Assumption", "Conflict", "Not Tested"):
            notes.append(f"{qtype} ({qstatus}): {as_text(question.get('description'))}")
    warnings = [issue for issue in issues if issue["level"] == "warning"]
    for warning in warnings[:10]:
        notes.append(f"Warning: {warning['message']}")
    if len(warnings) > 10:
        notes.append(f"... and {len(warnings) - 10} more warnings. See validate_workspace.py output.")
    if not notes:
        notes.append("None recorded.")
    full_width = sum(widths)
    for note in notes:
        merge_write(ws, row, 1, 6, note, font=SMALL_FONT)
        ws.row_dimensions[row].height = estimate_height([note], [full_width])
        row += 1

    row += 1
    row = section(ws, row, "How to read this workbook", 6)
    how_to = [
        "Test Cases is the full execution record; Defects is the triage view of confirmed failures only.",
        "Status vocabulary: Pass, Fail, Blocked, Needs Clarification, Observation, Not Run.",
        "Pass rate = Pass / (Pass + Fail); Blocked and Not Run are excluded and listed separately.",
        "Executed coverage = controls linked to an executed Pass/Fail case / controls inventoried.",
        "Reconciliation proves the counts: cases = sum of statuses; every Pass evidenced; every Fail linked & triaged; every defect linked.",
        "Anomaly triage filters test artifacts, expected variants and oracle gaps before raising defects.",
        "Evidence paths are workspace-relative files alongside this workbook.",
    ]
    for line in how_to:
        text = f"- {line}"
        merge_write(ws, row, 1, 6, text, font=SMALL_FONT)
        ws.row_dimensions[row].height = estimate_height([text], [full_width])
        row += 1

    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = f"A1:F{row - 1}"


# ---------------------------------------------------------------------------
# Detail sheets
# ---------------------------------------------------------------------------


def build_test_cases(wb: Workbook, loaded: dict) -> None:
    ws = wb.create_sheet("Test Cases")
    ws.sheet_properties.tabColor = BLUE
    headers = [
        "ID",
        "Module",
        "Path / Breadcrumb",
        "Title",
        "Category",
        "Technique",
        "Priority",
        "Reason",
        "Role",
        "Preconditions & Test Data",
        "Steps",
        "Oracle (type / source / confidence)",
        "Expected",
        "Actual",
        "Status",
        "Severity",
        "Defect Type",
        "Surfaces Checked",
        "Correlated Modules",
        "Relationships",
        "Atlas Refs",
        "Evidence",
        "Suggestion",
        "Notes",
        "Executed At",
        "Triage Disposition",
        "Triage Reason",
    ]
    widths = [10, 16, 28, 38, 20, 18, 8, 28, 14, 36, 46, 36, 36, 36, 16, 12, 18, 24, 20, 16, 16, 32, 32, 28, 18, 18, 34]
    set_widths(ws, widths)
    rows = []
    for case in loaded.get("test_cases") or []:
        preconditions = as_text(case.get("preconditions"))
        test_data = as_text(case.get("test_data"))
        combined = "\n".join(part for part in (preconditions, test_data) if part)
        triage = case.get("triage") if isinstance(case.get("triage"), dict) else {}
        rows.append(
            [
                case.get("id"),
                case.get("module"),
                case.get("path"),
                case.get("title"),
                case.get("category"),
                case.get("technique"),
                case.get("priority"),
                case.get("reason"),
                case.get("role"),
                combined,
                steps_text(case.get("steps")),
                oracle_text(case.get("oracle")),
                case.get("expected"),
                case.get("actual"),
                case.get("status"),
                case.get("severity"),
                case.get("defect_type"),
                as_text(case.get("surfaces_checked")),
                as_text(case.get("correlated_modules")),
                as_text(case.get("relationship_ids")),
                as_text(case.get("atlas_ids")),
                evidence_text(case.get("evidence")),
                case.get("suggestion"),
                case.get("notes"),
                case.get("executed_at"),
                triage.get("disposition"),
                triage.get("reason"),
            ]
        )
    # Column 15 (O) = Status, Column 16 (P) = Severity
    last_row = write_table(
        ws,
        1,
        headers,
        rows,
        widths,
        fill_map={15: STATUS_FILLS, 16: SEVERITY_FILLS},
        font_map={15: STATUS_FONTS, 16: SEVERITY_FONTS},
    )
    finish_sheet(ws, last_row, len(headers), freeze="C2")
    add_list_validation(ws, "O", STATUSES, last_row)
    add_list_validation(ws, "P", SEVERITIES, last_row)


def build_defects(wb: Workbook, loaded: dict) -> None:
    ws = wb.create_sheet("Defects")
    ws.sheet_properties.tabColor = "C00000"
    headers = [
        "ID",
        "Title",
        "Severity",
        "Type",
        "Module",
        "Path",
        "Test Cases",
        "Environment",
        "Preconditions",
        "Steps",
        "Expected",
        "Actual",
        "Evidence",
        "Impact",
        "Likely Cause",
        "Suggestion",
        "Workaround",
        "Status",
        "Notes",
    ]
    widths = [10, 40, 12, 18, 16, 26, 14, 30, 34, 44, 36, 36, 34, 34, 30, 34, 30, 14, 30]
    set_widths(ws, widths)
    defects = sorted(
        loaded.get("defects") or [],
        key=lambda d: (SEVERITY_RANK.get(as_text(d.get("severity")), 9), as_text(d.get("id"))),
    )
    rows = []
    for defect in defects:
        rows.append(
            [
                defect.get("id"),
                defect.get("title"),
                defect.get("severity"),
                defect.get("type"),
                defect.get("module"),
                defect.get("path"),
                as_text(defect.get("test_case_ids")),
                defect.get("environment"),
                defect.get("preconditions"),
                steps_text(defect.get("steps")),
                defect.get("expected"),
                defect.get("actual"),
                evidence_text(defect.get("evidence")),
                defect.get("impact"),
                defect.get("likely_cause"),
                defect.get("suggestion"),
                defect.get("workaround"),
                defect.get("status") or "Open",
                defect.get("notes"),
            ]
        )
    last_row = write_table(
        ws,
        1,
        headers,
        rows,
        widths,
        fill_map={3: SEVERITY_FILLS},
        font_map={3: SEVERITY_FONTS},
    )
    finish_sheet(ws, last_row, len(headers), freeze="B2")
    add_list_validation(ws, "C", SEVERITIES, last_row)
    add_list_validation(ws, "R", DEFECT_STATUSES, last_row)


def build_coverage(wb: Workbook, loaded: dict, stats: dict) -> None:
    ws = wb.create_sheet("Coverage")
    ws.sheet_properties.tabColor = "548235"
    ws.sheet_view.showGridLines = False
    widths = [28, 12, 14, 14, 10, 10, 10, 12, 20, 12, 10, 16]
    set_widths(ws, widths)

    row = section(ws, 1, "Coverage by module", 12)
    headers = [
        "Module",
        "Controls",
        "Executed",
        "Linked (All)",
        "Cases",
        "Pass",
        "Fail",
        "Blocked",
        "Needs Clarification",
        "Observation",
        "Not Run",
        "Executed Cov %",
    ]
    rows = [
        [
            r["module"],
            r["controls"],
            r["controls_executed"],
            r["controls_tested"],
            r["cases"],
            r["Pass"],
            r["Fail"],
            r["Blocked"],
            r["Needs Clarification"],
            r["Observation"],
            r["Not Run"],
            f"{r['coverage_pct']:.1f}%",
        ]
        for r in stats["module_rows"]
    ]
    row = write_table(ws, row, headers, rows, widths)
    merge_write(
        ws,
        row + 1,
        1,
        12,
        "Executed Cov % = controls linked to an executed Pass/Fail case / controls inventoried.",
        font=SMALL_FONT,
        border=False,
    )
    row += 3

    row = section(ws, row, "Module traceability", 12)
    headers = [
        "Module",
        "In Scope",
        "Controls",
        "Controls Covered",
        "Cases",
        "Fail",
        "Defects",
        "Unexplained Gaps",
        "Status",
    ]
    rows = [
        [
            r["module"],
            "Yes" if r["in_scope"] else "No",
            r["controls"],
            r["controls_explained"],
            r["cases"],
            r["Fail"],
            r["defects"],
            r["gaps"],
            r["status"],
        ]
        for r in stats["module_rows"]
    ]
    row = write_table(ws, row, headers, rows, widths[:9])
    merge_write(
        ws,
        row + 1,
        1,
        12,
        "An in-scope module with zero cases is a gap; in full/Exhaustive mode, uncovered controls without a reason are also gaps.",
        font=SMALL_FONT,
        border=False,
    )
    row += 3

    row = section(ws, row, "Coverage by test category", 12)
    headers = ["Category", "Cases", "Pass", "Fail", "Blocked", "Needs Clarification", "Observation", "Not Run"]
    rows = [
        [
            r["category"],
            r["cases"],
            r["Pass"],
            r["Fail"],
            r["Blocked"],
            r["Needs Clarification"],
            r["Observation"],
            r["Not Run"],
        ]
        for r in stats["category_rows"]
    ]
    if not rows:
        rows = [["(none)", 0, 0, 0, 0, 0, 0, 0]]
    row = write_table(ws, row, headers, rows, widths[:8])
    row += 2

    row = section(ws, row, "Relationship coverage", 12)
    headers = ["Metric", "Value", "Notes"]
    rows = [
        ["Relationships mapped", stats["relationships_total"], "Non-obvious cross-module / precedence / calculation edges"],
        ["Relationships executed", stats["relationships_executed"], "Linked to an executed Pass/Fail case"],
        ["Relationships linked (all)", stats["relationships_verified"], "Have at least one verified_by case"],
        ["Relationships not tested", stats["relationships_not_tested"], "Need a case or a stated not_tested_reason"],
        ["Executed relationship coverage", f"{stats['relationships_coverage_pct']:.1f}%", "Executed / mapped"],
    ]
    row = write_table(ws, row, headers, rows, [widths[0], widths[1], sum(widths[2:6])])
    row += 2

    row = section(ws, row, "Role coverage", 12)
    headers = ["Role", "Cases", "Notes"]
    roles = stats["roles"]
    rows = [
        [role, sum(1 for c in loaded.get("test_cases") or [] if as_text(c.get("role")) == role), ""]
        for role in roles
    ]
    if not rows:
        rows = [["(no roles recorded)", 0, "Add role to test cases to prove permission coverage."]]
    write_table(ws, row, headers, rows, [widths[0], widths[1], sum(widths[2:6])])
    ws.freeze_panes = "A2"


def build_atlas(wb: Workbook, loaded: dict) -> None:
    ws = wb.create_sheet("Field Atlas")
    ws.sheet_properties.tabColor = "7030A0"
    headers = [
        "ID",
        "State",
        "Module",
        "Path",
        "Label",
        "Control",
        "Required",
        "Default",
        "Options",
        "Constraints",
        "Helper Text",
        "Depends On",
        "Affects",
        "Roles Visible",
        "Tested By",
        "Not Tested Reason",
        "Notes",
    ]
    widths = [10, 10, 16, 34, 26, 18, 14, 14, 38, 28, 32, 26, 26, 18, 16, 30, 26]
    set_widths(ws, widths)
    rows = []
    for control in loaded.get("atlas") or []:
        rows.append(
            [
                control.get("id"),
                control.get("state_id"),
                control.get("module"),
                control.get("path"),
                control.get("label"),
                control.get("control"),
                control.get("required"),
                control.get("default"),
                as_text(control.get("options"), "; "),
                control.get("constraints"),
                control.get("helper_text"),
                control.get("depends_on"),
                control.get("affects"),
                as_text(control.get("roles_visible")),
                as_text(control.get("tested_by")),
                control.get("not_tested_reason"),
                control.get("notes"),
            ]
        )
    last_row = write_table(ws, 1, headers, rows, widths)
    finish_sheet(ws, last_row, len(headers), freeze="C2")


def build_relationships(wb: Workbook, loaded: dict) -> None:
    ws = wb.create_sheet("Relationships")
    ws.sheet_properties.tabColor = "BF8F00"
    headers = [
        "ID",
        "Source",
        "Target",
        "Type",
        "Description",
        "Evidence",
        "Confidence",
        "Verified By",
        "Not Tested Reason",
    ]
    widths = [10, 36, 36, 16, 44, 40, 12, 16, 30]
    set_widths(ws, widths)
    rows = []
    for relationship in loaded.get("relationships") or []:
        rows.append(
            [
                relationship.get("id"),
                relationship.get("source"),
                relationship.get("target"),
                relationship.get("type"),
                relationship.get("description"),
                relationship.get("evidence"),
                relationship.get("confidence"),
                as_text(relationship.get("verified_by")),
                relationship.get("not_tested_reason"),
            ]
        )
    last_row = write_table(ws, 1, headers, rows, widths)
    finish_sheet(ws, last_row, len(headers), freeze="C2")
    for row_index in range(2, last_row + 1):
        verified = ws.cell(row=row_index, column=8).value
        reason = ws.cell(row=row_index, column=9).value
        if not verified and not reason:
            ws.cell(row=row_index, column=8).fill = PatternFill("solid", fgColor="FFEB9C")
            ws.cell(row=row_index, column=9).fill = PatternFill("solid", fgColor="FFEB9C")


def build_data_config(wb: Workbook, loaded: dict) -> None:
    ws = wb.create_sheet("Test Data & Config")
    ws.sheet_properties.tabColor = "ED7D31"
    ws.sheet_view.showGridLines = False
    widths = [10, 28, 24, 14, 22, 18, 24, 26, 12, 20, 16, 28, 30]
    set_widths(ws, widths)

    row = section(ws, 1, "Test fixtures", 13)
    headers = ["ID", "Name", "Purpose", "Design", "Created Via", "Status", "Cleanup", "Notes"]
    rows = [
        [
            fixture.get("id"),
            fixture.get("name"),
            fixture.get("purpose"),
            fixture.get("design"),
            fixture.get("created_via"),
            fixture.get("status"),
            fixture.get("cleanup"),
            fixture.get("notes"),
        ]
        for fixture in loaded.get("fixtures") or []
    ]
    row = write_table(ws, row, headers, rows, widths[:8])
    row += 2

    row = section(ws, row, "Configuration changes", 13)
    headers = [
        "ID",
        "Path",
        "Setting",
        "Original",
        "Changed To",
        "Changed At",
        "Role",
        "Reason",
        "Restored",
        "Restored At",
        "Restored Value",
        "Evidence",
        "Notes",
    ]
    rows = [
        [
            change.get("id"),
            change.get("path"),
            change.get("setting"),
            change.get("original"),
            change.get("changed_to"),
            change.get("changed_at"),
            change.get("role"),
            change.get("reason"),
            "Yes" if change.get("restored") is True else "No",
            change.get("restored_at"),
            change.get("restored_value"),
            change.get("evidence"),
            change.get("notes"),
        ]
        for change in loaded.get("config_changes") or []
    ]
    last_row = write_table(ws, row, headers, rows, widths)
    for row_index in range(row + 1, last_row + 1):
        if ws.cell(row=row_index, column=9).value == "No":
            for col in range(1, 14):
                ws.cell(row=row_index, column=col).fill = PatternFill("solid", fgColor="FFC7CE")

    row = last_row + 2
    row = section(ws, row, "Configuration matrix", 13)
    headers = [
        "ID",
        "Area",
        "Setting",
        "Options",
        "Branch",
        "Profile Value",
        "Tested By",
        "Not Tested Reason",
    ]
    rows = [
        [
            entry.get("id"),
            entry.get("area"),
            entry.get("setting"),
            as_text(entry.get("options"), "; "),
            entry.get("branch"),
            entry.get("profile_value"),
            as_text(entry.get("tested_by")),
            entry.get("not_tested_reason"),
        ]
        for entry in loaded.get("configuration_matrix") or []
    ]
    row = write_table(ws, row, headers, rows, widths[:8])
    merge_write(
        ws,
        row + 1,
        1,
        13,
        "Every behavior-changing switch needs a valid profile_value and either tested_by or not_tested_reason.",
        font=SMALL_FONT,
        border=False,
    )
    ws.freeze_panes = "A2"


def build_questions(wb: Workbook, loaded: dict) -> None:
    ws = wb.create_sheet("Open Questions")
    ws.sheet_properties.tabColor = "808080"
    headers = ["ID", "Type", "Description", "Impact", "Owner", "Status", "Related"]
    widths = [10, 16, 60, 44, 18, 14, 24]
    set_widths(ws, widths)
    rows = [
        [
            question.get("id"),
            question.get("type"),
            question.get("description"),
            question.get("impact"),
            question.get("owner"),
            question.get("status") or "Open",
            as_text(question.get("related")),
        ]
        for question in loaded.get("questions") or []
    ]
    last_row = write_table(ws, 1, headers, rows, widths)
    finish_sheet(ws, last_row, len(headers), freeze="A2")


def build_guided_workbook(loaded: dict, output: Path) -> None:
    """Export an execution-ready guided sheet for environments without a browser tool."""
    wb = Workbook()
    meta = loaded.get("meta") or {}
    wb.properties.title = f"Guided Execution Sheet — {as_text(meta.get('app'))}"
    wb.properties.creator = "blackbox-ui-qa"

    ws = wb.active
    ws.title = "Guided Execution"
    ws.sheet_properties.tabColor = BLUE
    headers = [
        "Case ID",
        "Priority",
        "Module",
        "Path",
        "Role",
        "Title",
        "Preconditions & Test Data",
        "Exact Steps to Run",
        "Expected Result",
        "What to Capture & Evidence Path",
        "Observed Actual Result (Fill In)",
        "Status (Fill In)",
        "Tester Notes / Error Text",
    ]
    widths = [10, 10, 16, 26, 14, 34, 36, 48, 36, 36, 36, 18, 30]
    set_widths(ws, widths)

    rows = []
    for case in loaded.get("test_cases") or []:
        cid = as_text(case.get("id"))
        preconditions = as_text(case.get("preconditions"))
        test_data = as_text(case.get("test_data"))
        combined = "\n".join(part for part in (preconditions, test_data) if part)
        capture_hint = (
            f"Capture screenshot + console/network errors -> save under evidence/screenshots/{cid}.png"
        )
        rows.append(
            [
                cid,
                case.get("priority"),
                case.get("module"),
                case.get("path"),
                case.get("role"),
                case.get("title"),
                combined,
                steps_text(case.get("steps")),
                case.get("expected"),
                capture_hint,
                case.get("actual") if as_text(case.get("status")) != "Not Run" else "",
                case.get("status") if as_text(case.get("status")) != "Not Run" else "",
                case.get("notes"),
            ]
        )
    last_row = write_table(ws, 1, headers, rows, widths)
    finish_sheet(ws, last_row, len(headers), freeze="C2")
    add_list_validation(ws, "L", STATUSES, last_row)
    wb.save(output)


def build_defects_markdown(loaded: dict, path: Path, *, incomplete: bool) -> None:
    """Write developer-ready, severity-sorted DEFECTS.md tickets alongside the Excel report."""
    meta = loaded.get("meta") or {}
    cases_by_id = {
        as_text(c.get("id")): c
        for c in loaded.get("test_cases") or []
        if isinstance(c, dict) and as_text(c.get("id"))
    }
    defects = sorted(
        loaded.get("defects") or [],
        key=lambda d: (SEVERITY_RANK.get(as_text(d.get("severity")), 9), as_text(d.get("id"))),
    )

    lines = [
        f"# Defects — {as_text(meta.get('app')) or 'Application'}",
        "",
    ]
    if incomplete:
        lines.extend(["> [!WARNING]", "> DRAFT — validation errors remain. Resolve before external handoff.", ""])

    lines.extend(
        [
            f"- **Environment:** {as_text(meta.get('environment')) or 'unknown'} ({as_text(meta.get('url')) or 'no URL'})",
            f"- **Scope / Depth:** {as_text(meta.get('scope')) or 'N/A'} | {as_text(meta.get('depth')) or 'Deep'}",
            f"- **Total Defects:** {len(defects)}",
            "",
        ]
    )

    if not defects:
        lines.append("No confirmed defects recorded.")
    else:
        for defect in defects:
            did = as_text(defect.get("id"))
            title = as_text(defect.get("title"))
            severity = as_text(defect.get("severity"))
            dtype = as_text(defect.get("type"))
            status = as_text(defect.get("status")) or "Open"
            module = as_text(defect.get("module"))
            area = as_text(defect.get("path")) or module
            env = as_text(defect.get("environment")) or as_text(meta.get("environment"))
            tc_ids = [as_text(x) for x in as_list(defect.get("test_case_ids")) if as_text(x)]
            oracles = []
            for tid in tc_ids:
                tc = cases_by_id.get(tid)
                if tc and tc.get("oracle"):
                    oracles.append(f"{tid}: {oracle_text(tc.get('oracle'))}")

            lines.extend(
                [
                    "---",
                    "",
                    f"## [{did}] {title}",
                    "",
                    f"- **Severity:** `{severity}` | **Type:** `{dtype}` | **Status:** `{status}`",
                    f"- **Area:** `{area}` (Module: `{module}`)",
                    f"- **Test Cases:** {', '.join(tc_ids) if tc_ids else 'None'}",
                ]
            )
            if env:
                lines.append(f"- **Environment:** {env}")
            if oracles:
                lines.append(f"- **Oracle:** {' ; '.join(oracles)}")
            if as_text(defect.get("preconditions")):
                lines.append(f"- **Preconditions:** {as_text(defect.get('preconditions'))}")

            lines.extend(["", "### Reproduction Steps", ""])
            steps = as_list(defect.get("steps"))
            if steps:
                for idx, step in enumerate(steps, start=1):
                    lines.append(f"{idx}. {as_text(step)}")
            else:
                lines.append("1. (No steps recorded)")

            lines.extend(
                [
                    "",
                    f"**Expected:** {as_text(defect.get('expected'))}",
                    "",
                    f"**Actual:** {as_text(defect.get('actual'))}",
                    "",
                ]
            )
            if as_text(defect.get("impact")):
                lines.append(f"**Impact:** {as_text(defect.get('impact'))}\n")
            if as_text(defect.get("likely_cause")):
                lines.append(f"**Likely Cause:** {as_text(defect.get('likely_cause'))}\n")
            if as_text(defect.get("workaround")):
                lines.append(f"**Workaround:** {as_text(defect.get('workaround'))}\n")
            lines.append(f"**Suggested Fix:** {as_text(defect.get('suggestion'))}\n")

            ev_items = as_list(defect.get("evidence"))
            if ev_items:
                lines.append("**Evidence:**")
                for ev in ev_items:
                    lines.append(f"- `{as_text(ev)}`")
                lines.append("")

    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the blackbox-ui-qa v2.0 Excel report.")
    parser.add_argument("workspace", help="Workspace directory")
    parser.add_argument("--output", default="", help="Output .xlsx path")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Build a clearly marked draft even when validation errors remain",
    )
    parser.add_argument(
        "--guided-sheet",
        action="store_true",
        help="Export a guided execution workbook for human-driven runs (no browser)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    parser.add_argument("--validate-only", action="store_true", help="Validate and print counts, do not build")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--no-secret-scan", action="store_true", help="Skip the credential scan")
    parser.add_argument("--no-defects-md", action="store_true", help="Skip generating DEFECTS.md beside the workbook")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"Workspace not found: {workspace}", file=sys.stderr)
        return 1

    loaded = load_workspace(workspace)
    app_slug = slugify(as_text((loaded.get("meta") or {}).get("app")) or "app")
    stamp = datetime.now().strftime("%Y%m%d_%H%M")

    if args.guided_sheet:
        if not loaded.get("test_cases"):
            print("No test cases to export into guided sheet.", file=sys.stderr)
            return 1
        output = (
            Path(args.output).expanduser().resolve()
            if args.output
            else workspace / f"Guided_Execution_{app_slug}_{stamp}.xlsx"
        )
        if output.exists() and not args.force:
            print(f"Output already exists: {output}", file=sys.stderr)
            return 1
        output.parent.mkdir(parents=True, exist_ok=True)
        build_guided_workbook(loaded, output)
        print(f"Guided execution sheet written: {output}")
        return 0

    issues = validate_workspace(loaded, include_secret_scan=not args.no_secret_scan)
    errors = [issue for issue in issues if issue["level"] == "error"]
    warnings = [issue for issue in issues if issue["level"] == "warning"]
    if args.strict:
        errors = errors + warnings
    stats = coverage(loaded)

    if args.validate_only:
        print(f"Workspace: {workspace}")
        print(
            f"Controls: {stats['controls_total']} ({stats['controls_executed']} executed) | "
            f"Relationships: {stats['relationships_total']} ({stats['relationships_executed']} executed) | "
            f"Cases: {stats['cases_total']} | Defects: {len(loaded.get('defects') or [])}"
        )
        print(f"Errors: {len(errors)} | Warnings: {len(warnings)}")
        for issue in errors + warnings:
            print(f"- {issue['level'].upper()} {issue['code']}: {issue['message']}")
        return 1 if errors else 0

    if not loaded.get("test_cases") and not args.allow_incomplete:
        errors.append(
            {
                "level": "error",
                "code": "no_cases",
                "message": "No test cases recorded. Use --allow-incomplete for a draft, or execute tests first.",
                "ref": "",
            }
        )

    if errors and not args.allow_incomplete:
        print("Validation failed. Fix these errors or use --allow-incomplete for a draft:", file=sys.stderr)
        for issue in errors:
            print(f"- {issue['code']}: {issue['message']}", file=sys.stderr)
        return 1

    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else workspace / f"QA_Report_{app_slug}_{stamp}.xlsx"
    )
    if output.exists() and not args.force:
        print(f"Output already exists: {output}", file=sys.stderr)
        print("Use --force or a different --output.", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.properties.title = f"Blackbox UI QA Report — {as_text((loaded.get('meta') or {}).get('app'))}"
    wb.properties.creator = "blackbox-ui-qa"
    wb.properties.description = "Black-box UI QA report generated by blackbox-ui-qa v2.0."

    build_summary(wb, loaded, stats, issues, incomplete=bool(errors))
    build_test_cases(wb, loaded)
    build_defects(wb, loaded)
    build_coverage(wb, loaded, stats)
    build_atlas(wb, loaded)
    build_relationships(wb, loaded)
    build_data_config(wb, loaded)
    build_questions(wb, loaded)

    try:
        wb.save(output)
    except PermissionError:
        print(f"Cannot write {output}. Close the file if it is open in Excel.", file=sys.stderr)
        return 1

    print(f"Report written: {output}")
    if not args.no_defects_md:
        defects_md = output.parent / "DEFECTS.md"
        build_defects_markdown(loaded, defects_md, incomplete=bool(errors))
        print(f"Defects written: {defects_md}")
    print(
        f"Cases: {stats['cases_total']} | "
        f"Pass: {stats['status_counts'].get('Pass', 0)} | "
        f"Fail: {stats['status_counts'].get('Fail', 0)} | "
        f"Defects: {len(loaded.get('defects') or [])} | "
        f"Errors: {len(errors)} | Warnings: {len(warnings)}"
    )
    if errors:
        print("DRAFT: validation errors remain. The Summary sheet is marked accordingly.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
