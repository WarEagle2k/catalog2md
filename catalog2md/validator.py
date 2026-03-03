"""Validation pass: quality checks on the converted output."""
from __future__ import annotations

import re
from typing import Optional

from .models import (
    Chunk,
    ChunkType,
    Confidence,
    ConversionReport,
    PageResult,
)
from .part_numbers import extract_part_numbers, validate_part_number_density
from .tables import parse_markdown_table, validate_table, extract_tables_from_markdown


def validate_conversion(
    page_results: list[PageResult],
    chunks: list[Chunk],
    consolidated_md: str,
    source_filename: str,
) -> ConversionReport:
    """Run all quality checks and produce a report.
    
    Checks:
    1. No tables with mismatched column counts
    2. No truncated rows
    3. No missing sections vs page count
    4. No table split across chunk boundaries
    5. Part number density consistent with source
    """
    report = ConversionReport(source_file=source_filename)
    report.total_pages = len(page_results)
    report.pages_processed = sum(1 for pr in page_results if pr.markdown.strip())
    
    # Extraction method breakdown
    method_counts: dict[str, int] = {}
    for pr in page_results:
        method = pr.method.value
        method_counts[method] = method_counts.get(method, 0) + 1
    report.extraction_breakdown = method_counts
    
    # Chunk statistics
    report.chunk_count = len(chunks)
    type_counts: dict[str, int] = {}
    for chunk in chunks:
        t = chunk.chunk_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    report.chunk_type_breakdown = type_counts
    
    # Low confidence pages
    report.low_confidence_pages = [
        pr.page_num for pr in page_results
        if pr.confidence == Confidence.LOW
    ]
    
    # --- Quality Checks ---
    
    # Check 1: Table column consistency
    all_tables_valid = True
    total_tables = 0
    for pr in page_results:
        for table in pr.tables:
            total_tables += 1
            is_valid, msg = table.validate_column_consistency()
            if not is_valid:
                all_tables_valid = False
                report.flagged_issues.append(
                    f"Page {pr.page_num}: Table has {msg}"
                )
    report.total_tables = total_tables
    
    # Also validate tables in the consolidated markdown
    consolidated_tables = extract_tables_from_markdown(consolidated_md)
    for i, tbl_md in enumerate(consolidated_tables):
        is_valid, issues = validate_table(tbl_md)
        if not is_valid:
            for issue in issues:
                report.flagged_issues.append(
                    f"Consolidated MD table {i + 1}: {issue}"
                )
    
    # Check 2: No truncated rows (tables with very short rows)
    for pr in page_results:
        for table in pr.tables:
            headers, rows = parse_markdown_table(table.markdown)
            if not rows:
                continue
            avg_cells = sum(len(r) for r in rows) / len(rows)
            for j, row in enumerate(rows):
                if len(row) < avg_cells * 0.5 and len(row) < len(headers):
                    report.flagged_issues.append(
                        f"Page {pr.page_num}: Table row {j + 1} appears truncated "
                        f"({len(row)} cells vs {len(headers)} expected)"
                    )
    
    # Check 3: Missing sections vs page count
    pages_with_content = sum(1 for pr in page_results if pr.markdown.strip())
    if pages_with_content < report.total_pages * 0.7:
        report.flagged_issues.append(
            f"Only {pages_with_content}/{report.total_pages} pages produced content "
            f"({pages_with_content / report.total_pages:.0%})"
        )
    
    # Check 4: No table split across chunk boundaries
    for chunk in chunks:
        if chunk.chunk_type == ChunkType.TABLE:
            # Verify the table in this chunk is complete (has header + separator + at least 1 row)
            tables = extract_tables_from_markdown(chunk.content)
            for tbl in tables:
                lines = [l for l in tbl.strip().splitlines() if l.strip()]
                if len(lines) < 3:  # header + separator + at least 1 data row
                    report.flagged_issues.append(
                        f"Chunk {chunk.chunk_num}: Table appears incomplete "
                        f"(only {len(lines)} lines)"
                    )
    
    # Check 5: Part number density
    source_pns: list[str] = []
    for pr in page_results:
        source_pns.extend(pr.part_numbers)
    
    output_pns = extract_part_numbers(consolidated_md)
    report.total_part_numbers = len(set(source_pns))
    
    pn_valid, pn_msg = validate_part_number_density(source_pns, output_pns)
    if not pn_valid:
        report.flagged_issues.append(f"Part number check: {pn_msg}")
    
    # Overall validation
    report.validation_passed = len(report.flagged_issues) == 0
    
    return report
