"""Table handling: validation, merged header flattening, Markdown formatting."""
from __future__ import annotations

import re
from typing import Optional


def parse_markdown_table(md: str) -> tuple[list[str], list[list[str]]]:
    """Parse a Markdown table into headers and rows.
    
    Returns:
        Tuple of (headers, rows) where each is a list of cell strings.
    """
    lines = [l.strip() for l in md.strip().splitlines() if l.strip()]
    if not lines:
        return [], []
    
    def parse_row(line: str) -> list[str]:
        # Strip leading/trailing pipes and split
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [cell.strip() for cell in line.split("|")]
    
    headers = parse_row(lines[0])
    
    # Skip separator row(s) — lines with only dashes, colons, pipes, spaces
    rows = []
    for line in lines[1:]:
        if re.match(r'^[\s|:\-]+$', line):
            continue
        row = parse_row(line)
        rows.append(row)
    
    return headers, rows


def build_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a properly formatted Markdown table from headers and rows."""
    if not headers:
        return ""
    
    # Normalize row lengths to match header count
    col_count = len(headers)
    normalized_rows = []
    for row in rows:
        if len(row) < col_count:
            row = row + [""] * (col_count - len(row))
        elif len(row) > col_count:
            row = row[:col_count]
        normalized_rows.append(row)
    
    # Calculate column widths for alignment
    widths = [len(h) for h in headers]
    for row in normalized_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))
    
    # Build table
    lines = []
    # Header row
    header_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |"
    lines.append(header_line)
    # Separator
    sep_line = "| " + " | ".join("-" * w for w in widths) + " |"
    lines.append(sep_line)
    # Data rows
    for row in normalized_rows:
        data_line = "| " + " | ".join(
            cell.ljust(widths[i]) if i < len(widths) else cell
            for i, cell in enumerate(row)
        ) + " |"
        lines.append(data_line)
    
    return "\n".join(lines)


def flatten_merged_headers(
    headers: list[str],
    rows: list[list[str]],
    parent_context: Optional[str] = None,
) -> list[str]:
    """Flatten merged/spanned headers so every column is self-descriptive."""
    flattened = list(headers)
    
    # Phase 1: Fill empty headers by looking at context or position
    last_non_empty = ""
    for i, h in enumerate(flattened):
        if h.strip():
            last_non_empty = h.strip()
        elif last_non_empty:
            flattened[i] = f"{last_non_empty} ({i + 1})"
    
    # Phase 2: Expand known abbreviations in context of technical catalogs
    UNIT_EXPANSIONS = {
        "PSI": ("Pressure", "PSI"),
        "BAR": ("Pressure", "BAR"),
        "°F": ("Temperature", "°F"),
        "°C": ("Temperature", "°C"),
        "GPM": ("Flow Rate", "GPM"),
        "LPM": ("Flow Rate", "LPM"),
        "IN": ("Dimension", "in"),
        "MM": ("Dimension", "mm"),
        "LBS": ("Weight", "lbs"),
        "KG": ("Weight", "kg"),
        "CFM": ("Air Flow", "CFM"),
        "HP": ("Power", "HP"),
        "KW": ("Power", "kW"),
        "RPM": ("Speed", "RPM"),
        "BTU": ("Capacity", "BTU"),
    }
    
    for i, h in enumerate(flattened):
        h_upper = h.strip().upper()
        if h_upper in UNIT_EXPANSIONS:
            category, unit = UNIT_EXPANSIONS[h_upper]
            if parent_context:
                flattened[i] = f"{parent_context} ({unit})"
            else:
                flattened[i] = f"{category} ({unit})"
    
    # Phase 3: If a header is purely a number, it likely represents a size/rating
    for i, h in enumerate(flattened):
        if re.match(r'^\d+(\.\d+)?$', h.strip()):
            if parent_context:
                flattened[i] = f"{parent_context} {h.strip()}"
    
    return flattened


def validate_table(md: str) -> tuple[bool, list[str]]:
    """Validate a Markdown table for common issues."""
    issues = []
    headers, rows = parse_markdown_table(md)
    
    if not headers:
        issues.append("Table has no headers")
        return False, issues
    
    col_count = len(headers)
    
    empty_headers = [i for i, h in enumerate(headers) if not h.strip()]
    if empty_headers:
        issues.append(f"Empty headers at columns: {empty_headers}")
    
    for i, row in enumerate(rows):
        if len(row) != col_count:
            issues.append(
                f"Row {i + 1} has {len(row)} columns, expected {col_count}"
            )
    
    if rows:
        avg_cell_len = sum(
            sum(len(c) for c in row) / max(len(row), 1) for row in rows
        ) / len(rows)
        for i, row in enumerate(rows):
            row_avg = sum(len(c) for c in row) / max(len(row), 1)
            if row_avg < avg_cell_len * 0.1 and avg_cell_len > 5:
                issues.append(f"Row {i + 1} appears truncated (avg cell length: {row_avg:.1f} vs {avg_cell_len:.1f})")
    
    return len(issues) == 0, issues


def extract_tables_from_markdown(md: str) -> list[str]:
    """Extract individual Markdown tables from a mixed Markdown document."""
    tables = []
    lines = md.splitlines()
    in_table = False
    current_table: list[str] = []
    
    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        
        if is_table_line:
            if not in_table:
                in_table = True
                current_table = []
            current_table.append(line)
        else:
            if in_table:
                if len(current_table) >= 2:
                    tables.append("\n".join(current_table))
                in_table = False
                current_table = []
    
    if in_table and len(current_table) >= 2:
        tables.append("\n".join(current_table))
    
    return tables


def repair_table(md: str) -> str:
    """Attempt to repair a malformed Markdown table."""
    headers, rows = parse_markdown_table(md)
    if not headers:
        return md
    return build_markdown_table(headers, rows)
