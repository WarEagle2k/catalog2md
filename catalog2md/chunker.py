"""Table-aware chunking engine with YAML front-matter output."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import tiktoken

from .models import (
    Chunk,
    ChunkType,
    Confidence,
    PageResult,
)
from .part_numbers import extract_part_numbers
from .tables import extract_tables_from_markdown


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

_ENCODER: Optional[tiktoken.Encoding] = None


def _get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base."""
    return len(_get_encoder().encode(text))


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

# Regex for section headings in Markdown
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def _split_into_sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, content) pairs at heading boundaries.
    
    Content before the first heading gets heading = "".
    """
    sections: list[tuple[str, str]] = []
    matches = list(HEADING_RE.finditer(markdown))
    
    if not matches:
        return [("", markdown)]
    
    # Content before first heading
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


def _identify_tables_in_text(text: str) -> list[tuple[int, int, str]]:
    """Find table regions in text. Returns list of (start, end, table_string)."""
    tables = []
    lines = text.splitlines(keepends=True)
    in_table = False
    table_start = 0
    table_lines: list[str] = []
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


def _get_preceding_paragraph(text: str, table_start: int) -> str:
    """Get the paragraph immediately before a table position."""
    before = text[:table_start].rstrip()
    if not before:
        return ""
    
    # Find last blank line to get the paragraph
    last_blank = before.rfind("\n\n")
    if last_blank >= 0:
        para = before[last_blank:].strip()
    else:
        para = before.strip()
    
    # Don't return if it's another table or heading
    if para.startswith("|") or para.startswith("#"):
        return ""
    
    # Limit to reasonable length
    if count_tokens(para) > 100:
        # Take last ~100 tokens worth
        words = para.split()
        while count_tokens(" ".join(words)) > 100 and len(words) > 5:
            words = words[1:]
        para = " ".join(words)
    
    return para


def chunk_page_results(
    page_results: list[PageResult],
    source_filename: str,
    min_tokens: int = 512,
    max_tokens: int = 1024,
) -> list[Chunk]:
    """Apply table-aware chunking to extracted page results.
    
    Rules:
    - Each table is an atomic unit (never split)
    - Tables get prepended with section heading + preceding paragraph
    - Non-table content splits at section boundaries
    - Target chunk size: min_tokens to max_tokens (tables may exceed)
    """
    chunks: list[Chunk] = []
    chunk_num = 0
    
    # Build unified markdown with page markers
    current_heading = ""
    
    # Group page results into semantic sections
    text_accumulator: list[str] = []
    text_pages: list[int] = []
    
    for pr in page_results:
        if not pr.markdown.strip():
            continue
        
        content = pr.markdown
        page_num = pr.page_num
        
        # Split this page's content into sections
        sections = _split_into_sections(content)
        
        for heading, section_content in sections:
            if heading:
                current_heading = heading
            
            # Find tables in this section
            tables_in_section = _identify_tables_in_text(section_content)
            
            if not tables_in_section:
                # Pure text section — accumulate for potential merging
                text_accumulator.append(section_content)
                text_pages.append(page_num)
                
                # Flush if accumulated text is large enough
                combined = "\n\n".join(text_accumulator)
                if count_tokens(combined) >= min_tokens:
                    chunk_num += 1
                    page_range = _format_page_range(text_pages)
                    chunks.append(Chunk(
                        chunk_num=chunk_num,
                        chunk_type=ChunkType.TEXT,
                        content=_format_chunk_content(current_heading, combined),
                        section_heading=current_heading,
                        page_range=page_range,
                        source_file=source_filename,
                        token_count=count_tokens(combined),
                        part_numbers=extract_part_numbers(combined),
                    ))
                    text_accumulator = []
                    text_pages = []
                continue
            
            # Section has tables — flush any accumulated text first
            if text_accumulator:
                combined = "\n\n".join(text_accumulator)
                if combined.strip():
                    chunk_num += 1
                    page_range = _format_page_range(text_pages)
                    chunks.append(Chunk(
                        chunk_num=chunk_num,
                        chunk_type=ChunkType.TEXT,
                        content=_format_chunk_content(current_heading, combined),
                        section_heading=current_heading,
                        page_range=page_range,
                        source_file=source_filename,
                        token_count=count_tokens(combined),
                        part_numbers=extract_part_numbers(combined),
                    ))
                text_accumulator = []
                text_pages = []
            
            # Process each table as its own atomic chunk
            last_end = 0
            for tbl_start, tbl_end, tbl_str in tables_in_section:
                # Text before this table
                pre_text = section_content[last_end:tbl_start].strip()
                if pre_text and not pre_text.startswith("|"):
                    text_tokens = count_tokens(pre_text)
                    if text_tokens >= min_tokens // 2:
                        chunk_num += 1
                        chunks.append(Chunk(
                            chunk_num=chunk_num,
                            chunk_type=ChunkType.TEXT,
                            content=_format_chunk_content(current_heading, pre_text),
                            section_heading=current_heading,
                            page_range=str(page_num),
                            source_file=source_filename,
                            token_count=text_tokens,
                            part_numbers=extract_part_numbers(pre_text),
                        ))
                    else:
                        # Short pre-text — prepend to the table chunk
                        pass
                
                # The table chunk itself
                preceding = _get_preceding_paragraph(section_content, tbl_start)
                table_content = _format_table_chunk(
                    heading=current_heading,
                    preceding_text=preceding if not (pre_text and count_tokens(pre_text) >= min_tokens // 2) else pre_text,
                    table_md=tbl_str.strip(),
                )
                
                chunk_num += 1
                chunks.append(Chunk(
                    chunk_num=chunk_num,
                    chunk_type=ChunkType.TABLE,
                    content=table_content,
                    section_heading=current_heading,
                    page_range=str(page_num),
                    source_file=source_filename,
                    token_count=count_tokens(table_content),
                    part_numbers=extract_part_numbers(tbl_str),
                    tables_in_chunk=1,
                ))
                
                last_end = tbl_end
            
            # Text after last table in this section
            post_text = section_content[last_end:].strip()
            if post_text and not post_text.startswith("|"):
                text_accumulator.append(post_text)
                text_pages.append(page_num)
    
    # Flush remaining text
    if text_accumulator:
        combined = "\n\n".join(text_accumulator)
        if combined.strip():
            chunk_num += 1
            page_range = _format_page_range(text_pages)
            chunks.append(Chunk(
                chunk_num=chunk_num,
                chunk_type=ChunkType.TEXT,
                content=_format_chunk_content(current_heading, combined),
                section_heading=current_heading,
                page_range=page_range,
                source_file=source_filename,
                token_count=count_tokens(combined),
                part_numbers=extract_part_numbers(combined),
            ))
    
    # Post-process: split oversized text chunks (not tables — tables are atomic)
    final_chunks: list[Chunk] = []
    for chunk in chunks:
        if chunk.chunk_type == ChunkType.TABLE:
            final_chunks.append(chunk)
        elif chunk.token_count > max_tokens * 1.5:
            # Split at paragraph boundaries
            sub_chunks = _split_large_text_chunk(chunk, max_tokens)
            final_chunks.extend(sub_chunks)
        else:
            final_chunks.append(chunk)
    
    # Re-number chunks sequentially
    for i, chunk in enumerate(final_chunks, 1):
        chunk.chunk_num = i
    
    return final_chunks


def _format_chunk_content(heading: str, text: str) -> str:
    """Format chunk content with section heading."""
    parts = []
    if heading:
        parts.append(f"## {heading}\n")
    parts.append(text)
    return "\n".join(parts)


def _format_table_chunk(heading: str, preceding_text: str, table_md: str) -> str:
    """Format a table chunk with context to make it self-contained."""
    parts = []
    if heading:
        parts.append(f"## {heading}\n")
    if preceding_text and preceding_text.strip():
        parts.append(preceding_text.strip() + "\n")
    parts.append(table_md)
    return "\n".join(parts)


def _format_page_range(pages: list[int]) -> str:
    """Format a list of page numbers into a range string."""
    if not pages:
        return ""
    unique = sorted(set(pages))
    if len(unique) == 1:
        return str(unique[0])
    return f"{unique[0]}-{unique[-1]}"


def _split_large_text_chunk(chunk: Chunk, max_tokens: int) -> list[Chunk]:
    """Split a large text chunk at paragraph boundaries."""
    paragraphs = chunk.content.split("\n\n")
    sub_chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0
    
    for para in paragraphs:
        para_tokens = count_tokens(para)
        if current_tokens + para_tokens > max_tokens and current_parts:
            content = "\n\n".join(current_parts)
            sub_chunks.append(Chunk(
                chunk_num=0,  # Will be renumbered
                chunk_type=chunk.chunk_type,
                content=content,
                section_heading=chunk.section_heading,
                page_range=chunk.page_range,
                source_file=chunk.source_file,
                token_count=count_tokens(content),
                part_numbers=extract_part_numbers(content),
            ))
            current_parts = []
            current_tokens = 0
        current_parts.append(para)
        current_tokens += para_tokens
    
    if current_parts:
        content = "\n\n".join(current_parts)
        sub_chunks.append(Chunk(
            chunk_num=0,
            chunk_type=chunk.chunk_type,
            content=content,
            section_heading=chunk.section_heading,
            page_range=chunk.page_range,
            source_file=chunk.source_file,
            token_count=count_tokens(content),
            part_numbers=extract_part_numbers(content),
        ))
    
    return sub_chunks if sub_chunks else [chunk]
