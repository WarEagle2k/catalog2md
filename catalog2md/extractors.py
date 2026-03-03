"""Extraction engines: Docling (primary), pdfplumber (fallback), Claude vision (final fallback)."""
from __future__ import annotations

import base64
import io
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Optional

from rich.console import Console

from .models import (
    Confidence,
    ExtractionMethod,
    PageResult,
    TableData,
)
from .part_numbers import extract_part_numbers
from .tables import (
    extract_tables_from_markdown,
    flatten_merged_headers,
    parse_markdown_table,
    build_markdown_table,
    validate_table,
    repair_table,
)

console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Docling extractor
# ---------------------------------------------------------------------------

DOCLING_AVAILABLE = False
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import PdfFormatOption
    DOCLING_AVAILABLE = True
except ImportError:
    pass


class DoclingExtractor:
    """Primary extraction engine using IBM Docling."""

    def __init__(self):
        if not DOCLING_AVAILABLE:
            raise RuntimeError(
                "Docling is not installed. Install with: pip install docling --break-system-packages"
            )
        console.print("[dim]Initializing Docling (first run downloads ~2-3 GB of ML models)...[/dim]")
        pipeline_opts = PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=True,
        )
        pipeline_opts.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_opts.table_structure_options.do_cell_matching = True

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
            }
        )
        console.print("[green]Docling initialized.[/green]")

    def extract(self, pdf_path: str | Path) -> list[PageResult]:
        """Extract all pages from a PDF using Docling."""
        result = self.converter.convert(str(pdf_path))
        doc = result.document
        num_pages = doc.num_pages()
        page_results: list[PageResult] = []

        for page_num in range(1, num_pages + 1):
            try:
                md = doc.export_to_markdown(page_no=page_num)
                
                # Detect section headings from items on this page
                headings = []
                for item, depth in doc.iterate_items(page_no=page_num):
                    if hasattr(item, 'label') and str(item.label) == 'section_header':
                        headings.append(getattr(item, 'text', ''))
                
                # Extract and validate tables on this page
                tables = []
                for table in doc.tables:
                    if table.prov and table.prov[0].page_no == page_num:
                        # Pass doc= to avoid deprecation warning
                        table_md = table.export_to_markdown(doc=doc)
                        headers_raw, rows = parse_markdown_table(table_md)
                        
                        # Flatten merged headers
                        section_ctx = headings[-1] if headings else ""
                        headers_flat = flatten_merged_headers(headers_raw, rows, section_ctx)
                        
                        # Rebuild table with flattened headers
                        clean_md = build_markdown_table(headers_flat, rows)
                        
                        is_valid, issues = validate_table(clean_md)
                        if not is_valid:
                            clean_md = repair_table(clean_md)
                        
                        tables.append(TableData(
                            markdown=clean_md,
                            headers=headers_flat,
                            row_count=len(rows),
                            col_count=len(headers_flat),
                            page=page_num,
                            section_heading=section_ctx,
                            has_merged_headers=headers_raw != headers_flat,
                        ))
                
                part_nums = extract_part_numbers(md)
                confidence = Confidence.HIGH
                if not md.strip():
                    confidence = Confidence.LOW
                elif len(md.strip()) < 50:
                    confidence = Confidence.MEDIUM
                
                page_results.append(PageResult(
                    page_num=page_num,
                    method=ExtractionMethod.DOCLING,
                    confidence=confidence,
                    markdown=md,
                    tables=tables,
                    section_headings=headings,
                    part_numbers=part_nums,
                ))
            except Exception as e:
                page_results.append(PageResult(
                    page_num=page_num,
                    method=ExtractionMethod.DOCLING,
                    confidence=Confidence.LOW,
                    markdown="",
                    errors=[f"Docling extraction error: {e}"],
                ))

        return page_results


# ---------------------------------------------------------------------------
# pdfplumber extractor
# ---------------------------------------------------------------------------

class PdfPlumberExtractor:
    """Fallback extraction engine using pdfplumber."""

    def extract_page(self, pdf_path: str | Path, page_num: int) -> PageResult:
        """Extract a single page using pdfplumber (1-indexed)."""
        import pdfplumber

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                if page_num < 1 or page_num > len(pdf.pages):
                    return PageResult(
                        page_num=page_num,
                        method=ExtractionMethod.PDFPLUMBER,
                        confidence=Confidence.LOW,
                        markdown="",
                        errors=[f"Page {page_num} out of range (total: {len(pdf.pages)})"],
                    )
                
                page = pdf.pages[page_num - 1]
                
                raw_tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_y_tolerance": 5,
                    "snap_x_tolerance": 5,
                    "join_y_tolerance": 5,
                    "join_x_tolerance": 5,
                })
                
                if not raw_tables:
                    raw_tables = page.extract_tables({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                    })
                
                table_bboxes = []
                try:
                    found_tables = page.find_tables()
                    table_bboxes = [t.bbox for t in found_tables]
                except Exception:
                    pass
                
                if table_bboxes:
                    text_parts = []
                    text = page.extract_text() or ""
                else:
                    text = page.extract_text() or ""
                
                tables: list[TableData] = []
                md_parts = []
                
                headings = self._detect_headings(text)
                
                table_cell_values: set[str] = set()
                for raw_table in (raw_tables or []):
                    for raw_row in raw_table:
                        for cell in raw_row:
                            if cell:
                                for line in str(cell).splitlines():
                                    clean = line.strip()
                                    if clean and len(clean) > 2:
                                        table_cell_values.add(clean)
                
                if text.strip() and table_cell_values:
                    clean_lines = []
                    for line in text.splitlines():
                        stripped = line.strip()
                        if stripped and stripped not in table_cell_values:
                            clean_lines.append(line)
                    clean_text = "\n".join(clean_lines).strip()
                else:
                    clean_text = text.strip()
                
                if clean_text:
                    md_parts.append(clean_text)
                
                for raw_table in (raw_tables or []):
                    if not raw_table or len(raw_table) < 2:
                        continue
                    
                    flat_cells = [
                        str(c).strip() for row in raw_table for c in row if c
                    ]
                    if flat_cells:
                        fragment_count = sum(
                            1 for c in flat_cells
                            if len(c) > 10 and (
                                c[-1].isalpha() and ' ' in c and
                                not c.endswith(('in', 'mm', 'ft', 'lbs', 'kg', 'PSI', 'GPM', 'CFM'))
                            )
                        )
                        fragment_ratio = fragment_count / len(flat_cells)
                        if fragment_ratio > 0.3:
                            continue
                        
                        empty_ratio = sum(1 for c in flat_cells if not c) / len([str(c).strip() for row in raw_table for c in row])
                        non_empty = [c for c in flat_cells if c]
                        avg_cell_len = sum(len(c) for c in non_empty) / len(non_empty) if non_empty else 0
                        if avg_cell_len > 50 and empty_ratio > 0.3:
                            continue
                    
                    cleaned_table = []
                    for raw_row in raw_table:
                        cleaned_row = []
                        for cell in raw_row:
                            if cell is None:
                                cleaned_row.append("")
                            else:
                                cleaned_row.append(
                                    " ".join(str(cell).splitlines()).strip()
                                )
                        cleaned_table.append(cleaned_row)
                    
                    raw_headers = cleaned_table[0]
                    data_rows = cleaned_table[1:]
                    
                    if data_rows and all(
                        len(c) < 20 and not any(ch.isdigit() for ch in c)
                        for c in data_rows[0] if c
                    ):
                        merged_headers = [
                            f"{h} {r}".strip()
                            for h, r in zip(raw_headers, data_rows[0])
                        ]
                        raw_headers = merged_headers
                        data_rows = data_rows[1:]
                    
                    section_ctx = headings[-1] if headings else ""
                    flat_headers = flatten_merged_headers(raw_headers, data_rows, section_ctx)
                    
                    table_md = build_markdown_table(flat_headers, data_rows)
                    
                    is_valid, issues = validate_table(table_md)
                    if not is_valid:
                        table_md = repair_table(table_md)
                    
                    tables.append(TableData(
                        markdown=table_md,
                        headers=flat_headers,
                        row_count=len(data_rows),
                        col_count=len(flat_headers),
                        page=page_num,
                        section_heading=section_ctx,
                    ))
                    md_parts.append("\n" + table_md + "\n")
                
                full_md = "\n\n".join(md_parts)
                part_nums = extract_part_numbers(full_md)
                
                is_image = not text.strip() and not raw_tables
                confidence = Confidence.LOW if is_image else (
                    Confidence.MEDIUM if len(text.strip()) < 50 else Confidence.HIGH
                )
                
                return PageResult(
                    page_num=page_num,
                    method=ExtractionMethod.PDFPLUMBER,
                    confidence=confidence,
                    markdown=full_md,
                    tables=tables,
                    section_headings=headings,
                    part_numbers=part_nums,
                    is_image_based=is_image,
                )
        except Exception as e:
            return PageResult(
                page_num=page_num,
                method=ExtractionMethod.PDFPLUMBER,
                confidence=Confidence.LOW,
                markdown="",
                errors=[f"pdfplumber extraction error: {e}"],
            )

    def extract_all(self, pdf_path: str | Path) -> list[PageResult]:
        """Extract all pages."""
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            num_pages = len(pdf.pages)
        return [self.extract_page(pdf_path, i) for i in range(1, num_pages + 1)]

    @staticmethod
    def _detect_headings(text: str) -> list[str]:
        """Heuristic heading detection from raw text."""
        headings = []
        lines = text.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if (
                stripped.isupper() and 3 < len(stripped) < 80
                and not stripped.startswith("|")
                and not re.match(r'^[\d\s\.\-]+$', stripped)
            ):
                headings.append(stripped.title())
            elif (
                len(stripped) < 60
                and re.match(r'^[\d]+[\.\)]\s+\S', stripped)
            ):
                headings.append(stripped)
        return headings


# ---------------------------------------------------------------------------
# Claude Vision extractor
# ---------------------------------------------------------------------------

class ClaudeVisionExtractor:
    """Final fallback: uses Claude's vision API to interpret PDF page images."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Pass via --api-key or set the environment variable."
            )

    def extract_page(self, pdf_path: str | Path, page_num: int) -> PageResult:
        """Convert a single page to an image and send to Claude for interpretation."""
        try:
            from pdf2image import convert_from_path
            import anthropic
        except ImportError as e:
            return PageResult(
                page_num=page_num,
                method=ExtractionMethod.CLAUDE_VISION,
                confidence=Confidence.LOW,
                markdown="",
                errors=[f"Missing dependency for Claude vision: {e}"],
            )

        try:
            images = convert_from_path(
                str(pdf_path),
                first_page=page_num,
                last_page=page_num,
                dpi=200,
                fmt="png",
            )
            if not images:
                return PageResult(
                    page_num=page_num,
                    method=ExtractionMethod.CLAUDE_VISION,
                    confidence=Confidence.LOW,
                    markdown="",
                    errors=["Failed to render page as image"],
                )

            img_buffer = io.BytesIO()
            images[0].save(img_buffer, format="PNG")
            img_b64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")

            client = anthropic.Anthropic(api_key=self.api_key)

            prompt = """Analyze this technical catalog page and convert it to clean Markdown. Follow these rules precisely:

1. **Tables**: Convert every table to a Markdown table with pipe delimiters. Ensure:
   - Every column has a fully descriptive header (expand abbreviations: "PSI" \u2192 "Max Pressure (PSI)")
   - All rows are included \u2014 never skip or truncate data
   - Column counts are consistent across all rows
   - Merged/spanned headers are flattened so each column stands alone

2. **Section headings**: Use Markdown heading levels (##, ###) to reflect the document hierarchy.

3. **Part numbers**: Any alphanumeric strings that look like industrial part numbers (e.g., AH-350, 12345-001, VLV-2001A) must be preserved exactly. Never split them across lines.

4. **Specifications and dimensions**: Preserve all numerical data, units, and ratings exactly as shown.

5. **Layout**: If the page has multiple columns, merge them into a single-column flow in reading order.

6. **Images/diagrams**: Replace with a placeholder: `<!-- FIGURE: brief description -->`

Return ONLY the Markdown content \u2014 no explanation, no code fences."""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": img_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            md = response.content[0].text.strip()
            
            if md.startswith("```markdown"):
                md = md[len("```markdown"):].strip()
            if md.startswith("```"):
                md = md[3:].strip()
            if md.endswith("```"):
                md = md[:-3].strip()

            table_strings = extract_tables_from_markdown(md)
            tables = []
            for tbl_md in table_strings:
                headers, rows = parse_markdown_table(tbl_md)
                tables.append(TableData(
                    markdown=tbl_md,
                    headers=headers,
                    row_count=len(rows),
                    col_count=len(headers),
                    page=page_num,
                ))

            headings = re.findall(r'^#{1,4}\s+(.+)$', md, re.MULTILINE)
            part_nums = extract_part_numbers(md)

            return PageResult(
                page_num=page_num,
                method=ExtractionMethod.CLAUDE_VISION,
                confidence=Confidence.MEDIUM,
                markdown=md,
                tables=tables,
                section_headings=headings,
                part_numbers=part_nums,
            )

        except Exception as e:
            return PageResult(
                page_num=page_num,
                method=ExtractionMethod.CLAUDE_VISION,
                confidence=Confidence.LOW,
                markdown="",
                errors=[f"Claude vision error: {e}"],
            )


# ---------------------------------------------------------------------------
# Orchestrator: tries extractors in order with fallback
# ---------------------------------------------------------------------------

class ExtractionOrchestrator:
    """Manages the extraction pipeline with fallback logic."""

    def __init__(
        self,
        use_docling: bool = True,
        anthropic_api_key: Optional[str] = None,
        force_method: Optional[ExtractionMethod] = None,
    ):
        self.docling: Optional[DoclingExtractor] = None
        self.plumber = PdfPlumberExtractor()
        self.claude: Optional[ClaudeVisionExtractor] = None
        self.force_method = force_method

        if use_docling and DOCLING_AVAILABLE and force_method != ExtractionMethod.PDFPLUMBER:
            try:
                self.docling = DoclingExtractor()
            except Exception as e:
                console.print(f"[yellow]Docling unavailable: {e}[/yellow]")

        if anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"):
            try:
                self.claude = ClaudeVisionExtractor(api_key=anthropic_api_key)
            except Exception as e:
                console.print(f"[yellow]Claude vision unavailable: {e}[/yellow]")

    def extract(self, pdf_path: str | Path, status_callback=None) -> list[PageResult]:
        """Extract all pages, using fallback cascade as needed."""
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            num_pages = len(pdf.pages)

        if self.docling and self.force_method != ExtractionMethod.PDFPLUMBER:
            if status_callback:
                status_callback("Extracting with Docling...")
            try:
                results = self.docling.extract(pdf_path)
                if len(results) == num_pages:
                    final_results = []
                    for pr in results:
                        if self._needs_fallback(pr):
                            fallback = self._fallback_extract(pdf_path, pr.page_num, status_callback)
                            final_results.append(fallback)
                        else:
                            final_results.append(pr)
                    return final_results
            except Exception as e:
                console.print(f"[yellow]Docling failed for entire document: {e}[/yellow]")

        results: list[PageResult] = []
        for page_num in range(1, num_pages + 1):
            if status_callback:
                status_callback(f"Extracting page {page_num}/{num_pages}...")

            if self.force_method == ExtractionMethod.CLAUDE_VISION and self.claude:
                pr = self.claude.extract_page(pdf_path, page_num)
            else:
                pr = self.plumber.extract_page(pdf_path, page_num)
                if self._needs_fallback(pr):
                    pr = self._fallback_extract(pdf_path, page_num, status_callback)
            
            results.append(pr)

        return results

    def _needs_fallback(self, pr: PageResult) -> bool:
        if pr.confidence == Confidence.LOW:
            return True
        if pr.is_image_based:
            return True
        for table in pr.tables:
            is_valid, _ = table.validate_column_consistency()
            if not is_valid:
                return True
        return False

    def _fallback_extract(self, pdf_path, page_num, status_callback=None):
        pr = self.plumber.extract_page(pdf_path, page_num)
        if not self._needs_fallback(pr):
            return pr
        if self.claude:
            if status_callback:
                status_callback(f"Page {page_num}: falling back to Claude vision...")
            return self.claude.extract_page(pdf_path, page_num)
        pr.confidence = Confidence.LOW
        return pr
