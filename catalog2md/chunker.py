"""Table-aware chunking engine with YAML front-matter output."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import tiktoken

from .models import Chunk, ChunkType, Confidence, PageResult
from .part_numbers import extract_part_numbers
from .tables import extract_tables_from_markdown


_ENCODER: Optional[tiktoken.Encoding] = None

def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER

def count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def _split_into_sections(markdown):
    sections = []
    matches = list(HEADING_RE.finditer(markdown))
    if not matches:
        return [("", markdown)]
    if matches[0].start() > 0:
        pre_content = markdown[:matches[0].start()].strip()
        if pre_content:
            sections.append(("", pre_content))
    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        content = markdown[start:end].strip()
        sections.append((heading, content))
    return sections


def _identify_tables_in_text(text):
    tables = []
    lines = text.splitlines(keepends=True)
    in_table = False
    table_start = 0
    table_lines = []
    pos = 0
    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        if is_table_line:
            if not in_table:
                in_table = True
                table_start = pos
                table_lines = []
            table_lines.append(line)
        else:
            if in_table:
                if len(table_lines) >= 2:
                    table_str = "".join(table_lines)
                    tables.append((table_start, pos, table_str))
                in_table = False
                table_lines = []
        pos += len(line)
    if in_table and len(table_lines) >= 2:
        table_str = "".join(table_lines)
        tables.append((table_start, pos, table_str))
    return tables


def _get_preceding_paragraph(text, table_start):
    before = text[:table_start].rstrip()
    if not before:
        return ""
    last_blank = before.rfind("\n\n")
    if last_blank >= 0:
        return before[last_blank:].strip()
    return before.strip()


def chunk_page_results(
    page_results: list[PageResult],
    source_filename: str,
    min_tokens: int = 512,
    max_tokens: int = 1024,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_num = 0
    current_text = ""
    current_heading = ""
    current_pages: list[int] = []
    current_tables = 0
    current_part_numbers: list[str] = []

    def flush_text_chunk():
        nonlocal chunk_num, current_text, current_heading, current_pages, current_tables, current_part_numbers
        if not current_text.strip():
            return
        chunk_num += 1
        tokens = count_tokens(current_text)
        pns = extract_part_numbers(current_text)
        page_range = f"{min(current_pages)}-{max(current_pages)}" if current_pages else "0-0"
        chunk_type = ChunkType.MIXED if current_tables > 0 else ChunkType.TEXT
        chunks.append(Chunk(
            chunk_num=chunk_num,
            chunk_type=chunk_type,
            content=current_text.strip(),
            section_heading=current_heading,
            page_range=page_range,
            source_file=source_filename,
            token_count=tokens,
            part_numbers=pns,
            tables_in_chunk=current_tables,
        ))
        current_text = ""
        current_pages = []
        current_tables = 0
        current_part_numbers = []

    for pr in page_results:
        if not pr.markdown.strip():
            continue
        page_md = pr.markdown
        tables_in_page = _identify_tables_in_text(page_md)
        if pr.section_headings:
            current_heading = pr.section_headings[-1]
        if not tables_in_page:
            test_text = current_text + "\n\n" + page_md if current_text else page_md
            if count_tokens(test_text) > max_tokens and current_text:
                flush_text_chunk()
            current_text = (current_text + "\n\n" + page_md).strip() if current_text else page_md
            current_pages.append(pr.page_num)
        else:
            last_end = 0
            for tbl_start, tbl_end, tbl_str in tables_in_page:
                pre_text = page_md[last_end:tbl_start].strip()
                if pre_text:
                    test_text = current_text + "\n\n" + pre_text if current_text else pre_text
                    if count_tokens(test_text) > max_tokens and current_text:
                        flush_text_chunk()
                    current_text = (current_text + "\n\n" + pre_text).strip() if current_text else pre_text
                    current_pages.append(pr.page_num)
                if current_text.strip():
                    flush_text_chunk()
                chunk_num += 1
                tbl_tokens = count_tokens(tbl_str)
                tbl_pns = extract_part_numbers(tbl_str)
                preceding = _get_preceding_paragraph(page_md, tbl_start)
                table_content = (preceding + "\n\n" + tbl_str).strip() if preceding else tbl_str
                chunks.append(Chunk(
                    chunk_num=chunk_num,
                    chunk_type=ChunkType.TABLE,
                    content=table_content,
                    section_heading=current_heading,
                    page_range=str(pr.page_num),
                    source_file=source_filename,
                    token_count=count_tokens(table_content),
                    part_numbers=tbl_pns,
                    tables_in_chunk=1,
                ))
                last_end = tbl_end
            post_text = page_md[last_end:].strip()
            if post_text:
                current_text = (current_text + "\n\n" + post_text).strip() if current_text else post_text
                current_pages.append(pr.page_num)
    flush_text_chunk()
    return chunks
