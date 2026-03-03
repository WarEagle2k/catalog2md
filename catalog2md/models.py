"""Data models used throughout the pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ExtractionMethod(str, Enum):
    DOCLING = "docling"
    PDFPLUMBER = "pdfplumber"
    CLAUDE_VISION = "claude_vision"
    SKIPPED = "skipped"


class ChunkType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    MIXED = "mixed"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class TableData:
    """A validated Markdown table with metadata."""
    markdown: str
    headers: list[str]
    row_count: int
    col_count: int
    page: int
    section_heading: str = ""
    preceding_text: str = ""
    has_merged_headers: bool = False

    def validate_column_consistency(self) -> tuple[bool, str]:
        """Check that every row in the Markdown table has the same column count."""
        lines = [l for l in self.markdown.strip().splitlines() if l.strip().startswith("|")]
        if not lines:
            return False, "No table rows found"
        counts = []
        for line in lines:
            cells = [c for c in line.split("|") if c.strip() and not re.match(r'^[\s\-:]+$', c)]
            counts.append(len(cells))
        data_counts = [c for c in counts if c > 0]
        if not data_counts:
            return False, "No data cells found"
        if len(set(data_counts)) > 1:
            return False, f"Mismatched column counts: {data_counts}"
        return True, "OK"


@dataclass
class PageResult:
    """Extraction result for a single page."""
    page_num: int
    method: ExtractionMethod
    confidence: Confidence
    markdown: str
    tables: list[TableData] = field(default_factory=list)
    section_headings: list[str] = field(default_factory=list)
    part_numbers: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    is_image_based: bool = False


@dataclass
class Chunk:
    """A single output chunk."""
    chunk_num: int
    chunk_type: ChunkType
    content: str
    section_heading: str
    page_range: str
    source_file: str
    token_count: int = 0
    part_numbers: list[str] = field(default_factory=list)
    tables_in_chunk: int = 0

    def to_yaml_frontmatter(self) -> str:
        """Generate YAML front-matter block."""
        import yaml
        meta = {
            "source_file": self.source_file,
            "chunk_number": self.chunk_num,
            "chunk_type": self.chunk_type.value,
            "section_heading": self.section_heading or "(no heading)",
            "page_range": self.page_range,
            "token_count": self.token_count,
        }
        if self.part_numbers:
            meta["part_numbers"] = self.part_numbers
        if self.tables_in_chunk > 0:
            meta["tables_in_chunk"] = self.tables_in_chunk
        return f"---\n{yaml.dump(meta, default_flow_style=False, sort_keys=False)}---\n"

    def to_file_content(self) -> str:
        """Full chunk file content with YAML front-matter."""
        return self.to_yaml_frontmatter() + "\n" + self.content


@dataclass
class ConversionReport:
    """Summary report for a conversion run."""
    source_file: str
    total_pages: int = 0
    pages_processed: int = 0
    extraction_breakdown: dict[str, int] = field(default_factory=dict)
    chunk_count: int = 0
    chunk_type_breakdown: dict[str, int] = field(default_factory=dict)
    flagged_issues: list[str] = field(default_factory=list)
    low_confidence_pages: list[int] = field(default_factory=list)
    total_tables: int = 0
    total_part_numbers: int = 0
    validation_passed: bool = True
