"""Output writer: produces consolidated .md, chunk files, and YAML front-matter."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from .models import (
    Chunk,
    Confidence,
    ConversionReport,
    ExtractionMethod,
    PageResult,
)


def write_consolidated_markdown(
    page_results: list[PageResult],
    output_path: Path,
    source_filename: str,
) -> str:
    """Write a single consolidated .md file with YAML front-matter.
    
    Returns the full Markdown content written.
    """
    # Build extraction method per page
    method_per_page: dict[int, str] = {}
    for pr in page_results:
        method_per_page[pr.page_num] = pr.method.value
    
    # Front-matter
    front_matter = {
        "source_file": source_filename,
        "page_count": len(page_results),
        "extraction_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extraction_method_per_page": method_per_page,
        "total_chunk_count": 0,  # Will be updated after chunking
    }
    
    yaml_block = f"---\n{yaml.dump(front_matter, default_flow_style=False, sort_keys=False)}---\n\n"
    
    # Build content
    content_parts: list[str] = [yaml_block]
    
    for pr in page_results:
        if not pr.markdown.strip():
            content_parts.append(f"\n<!-- PAGE {pr.page_num} - No content extracted -->\n")
            continue
        
        # Low confidence flag
        if pr.confidence == Confidence.LOW:
            content_parts.append(f"\n<!-- LOW_CONFIDENCE_PAGE: {pr.page_num} -->\n")
        
        # Page marker (as HTML comment for clean Markdown)
        content_parts.append(f"\n<!-- PAGE {pr.page_num} | method: {pr.method.value} -->\n")
        
        content_parts.append(pr.markdown)
        content_parts.append("\n")
    
    full_content = "\n".join(content_parts)
    
    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_content, encoding="utf-8")
    
    return full_content


def update_consolidated_chunk_count(output_path: Path, chunk_count: int):
    """Update the total_chunk_count in the front-matter of the consolidated file."""
    content = output_path.read_text(encoding="utf-8")
    content = content.replace(
        "total_chunk_count: 0",
        f"total_chunk_count: {chunk_count}",
    )
    output_path.write_text(content, encoding="utf-8")


def write_chunk_files(
    chunks: list[Chunk],
    output_dir: Path,
    catalog_name: str,
):
    """Write individual chunk files to the chunks subdirectory."""
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    
    for chunk in chunks:
        filename = f"{catalog_name}_chunk_{chunk.chunk_num:03d}.md"
        filepath = chunks_dir / filename
        filepath.write_text(chunk.to_file_content(), encoding="utf-8")


def write_report(
    report: ConversionReport,
    output_dir: Path,
    catalog_name: str,
):
    """Write a YAML report file summarizing the conversion."""
    report_data = {
        "source_file": report.source_file,
        "total_pages": report.total_pages,
        "pages_processed": report.pages_processed,
        "extraction_breakdown": report.extraction_breakdown,
        "chunk_count": report.chunk_count,
        "chunk_type_breakdown": report.chunk_type_breakdown,
        "total_tables": report.total_tables,
        "total_part_numbers": report.total_part_numbers,
        "low_confidence_pages": report.low_confidence_pages,
        "validation_passed": report.validation_passed,
        "flagged_issues": report.flagged_issues,
    }
    
    report_path = output_dir / f"{catalog_name}_report.yaml"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        yaml.dump(report_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
