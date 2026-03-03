"""Validation pass: quality checks on the converted output."""
from __future__ import annotations

import re
from typing import Optional

from .models import Chunk, ChunkType, Confidence, ConversionReport, PageResult
from .part_numbers import extract_part_numbers, validate_part_number_density
from .tables import parse_markdown_table, validate_table, extract_tables_from_markdown


def validate_conversion(page_results, chunks, consolidated_md, source_filename):
    report = ConversionReport(source_file=source_filename)
    report.total_pages = len(page_results)
    report.pages_processed = sum(1 for pr in page_results if pr.markdown.strip())
    method_counts = {}
    for pr in page_results:
        method = pr.method.value
        method_counts[method] = method_counts.get(method, 0) + 1
    report.extraction_breakdown = method_counts
    report.chunk_count = len(chunks)
    type_counts = {}
    for chunk in chunks:
        t = chunk.chunk_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    report.chunk_type_breakdown = type_counts
    report.low_confidence_pages = [pr.page_num for pr in page_results if pr.confidence == Confidence.LOW]
    total_tables = 0
    for pr in page_results:
        for table in pr.tables:
            total_tables += 1
            is_valid, msg = table.validate_column_consistency()
            if not is_valid:
                report.flagged_issues.append(f"Page {pr.page_num}: Table has {msg}")
    report.total_tables = total_tables
    consolidated_tables = extract_tables_from_markdown(consolidated_md)
    for i, tbl_md in enumerate(consolidated_tables):
        is_valid, issues = validate_table(tbl_md)
        if not is_valid:
            for issue in issues:
                report.flagged_issues.append(f"Consolidated MD table {i + 1}: {issue}")
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
    pages_with_content = sum(1 for pr in page_results if pr.markdown.strip())
    if pages_with_content < report.total_pages * 0.7:
        report.flagged_issues.append(
            f"Only {pages_with_content}/{report.total_pages} pages produced content "
            f"({pages_with_content / report.total_pages:.0%})"
        )
    for chunk in chunks:
        if chunk.chunk_type == ChunkType.TABLE:
            tables = extract_tables_from_markdown(chunk.content)
            for tbl in tables:
                lines = [l for l in tbl.strip().splitlines() if l.strip()]
                if len(lines) < 3:
                    report.flagged_issues.append(
                        f"Chunk {chunk.chunk_num}: Table appears incomplete (only {len(lines)} lines)"
                    )
    source_pns = []
    for pr in page_results:
        source_pns.extend(pr.part_numbers)
    output_pns = extract_part_numbers(consolidated_md)
    report.total_part_numbers = len(set(source_pns))
    pn_valid, pn_msg = validate_part_number_density(source_pns, output_pns)
    if not pn_valid:
        report.flagged_issues.append(f"Part number check: {pn_msg}")
    report.validation_passed = len(report.flagged_issues) == 0
    return report
