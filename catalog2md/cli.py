#!/usr/bin/env python3
"""catalog2md — CLI tool to convert technical PDF catalogs to RAG-optimized Markdown.

Usage:
    python -m catalog2md input.pdf -o ./output
    python -m catalog2md ./pdf_directory/ -o ./output
    python -m catalog2md input.pdf -o ./output --api-key sk-ant-...
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich import box

from .extractors import ExtractionOrchestrator, DOCLING_AVAILABLE
from .chunker import chunk_page_results, count_tokens
from .validator import validate_conversion
from .writer import (
    write_consolidated_markdown,
    update_consolidated_chunk_count,
    write_chunk_files,
    write_report,
)
from .models import ExtractionMethod

console = Console()


def find_pdfs(input_path: Path) -> list[Path]:
    """Find all PDF files from the input path (file or directory)."""
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    elif input_path.is_dir():
        pdfs = sorted(input_path.glob("**/*.pdf"))
        if not pdfs:
            console.print(f"[red]No PDF files found in {input_path}[/red]")
            sys.exit(1)
        return pdfs
    else:
        console.print(f"[red]Input must be a PDF file or directory: {input_path}[/red]")
        sys.exit(1)


def sanitize_name(filename: str) -> str:
    """Create a clean name from a filename for use in output paths."""
    stem = Path(filename).stem
    # Replace non-alphanumeric chars with underscores
    clean = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    # Collapse multiple underscores
    clean = "_".join(part for part in clean.split("_") if part)
    return clean.lower()


def process_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    orchestrator: ExtractionOrchestrator,
    min_chunk_tokens: int = 512,
    max_chunk_tokens: int = 1024,
) -> None:
    """Process a single PDF through the full pipeline."""
    catalog_name = sanitize_name(pdf_path.name)
    pdf_output_dir = output_dir / catalog_name
    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Processing:[/bold blue] {pdf_path.name}")
    start_time = time.time()

    # -----------------------------------------------------------------------
    # Step 1: Extraction
    # -----------------------------------------------------------------------
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting pages...", total=None)

        def status_cb(msg: str):
            progress.update(task, description=msg)

        page_results = orchestrator.extract(pdf_path, status_callback=status_cb)
        progress.update(task, description="Extraction complete", completed=100, total=100)

    console.print(f"  Extracted [green]{len(page_results)}[/green] pages")

    # -----------------------------------------------------------------------
    # Step 2: Write consolidated Markdown
    # -----------------------------------------------------------------------
    consolidated_path = pdf_output_dir / f"{catalog_name}.md"
    consolidated_md = write_consolidated_markdown(
        page_results, consolidated_path, pdf_path.name
    )
    console.print(f"  Written consolidated file: [cyan]{consolidated_path.name}[/cyan]")

    # -----------------------------------------------------------------------
    # Step 3: Chunking
    # -----------------------------------------------------------------------
    chunks = chunk_page_results(
        page_results,
        source_filename=pdf_path.name,
        min_tokens=min_chunk_tokens,
        max_tokens=max_chunk_tokens,
    )
    console.print(f"  Generated [green]{len(chunks)}[/green] chunks")

    # Update chunk count in consolidated file
    update_consolidated_chunk_count(consolidated_path, len(chunks))

    # Write chunk files
    write_chunk_files(chunks, pdf_output_dir, catalog_name)
    console.print(f"  Written chunk files to: [cyan]{catalog_name}/chunks/[/cyan]")

    # -----------------------------------------------------------------------
    # Step 4: Validation
    # -----------------------------------------------------------------------
    report = validate_conversion(
        page_results, chunks, consolidated_md, pdf_path.name
    )

    # Write report
    write_report(report, pdf_output_dir, catalog_name)

    elapsed = time.time() - start_time

    # -----------------------------------------------------------------------
    # Step 5: Display summary
    # -----------------------------------------------------------------------
    _print_summary(report, elapsed, pdf_output_dir)


def _print_summary(report, elapsed: float, output_dir: Path):
    """Print a rich summary table for a conversion run."""
    
    # Main stats table
    stats = Table(
        title=f"Conversion Summary: {report.source_file}",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold",
    )
    stats.add_column("Metric", style="cyan")
    stats.add_column("Value", justify="right")
    
    stats.add_row("Pages Total", str(report.total_pages))
    stats.add_row("Pages Processed", str(report.pages_processed))
    stats.add_row("Total Chunks", str(report.chunk_count))
    stats.add_row("Total Tables", str(report.total_tables))
    stats.add_row("Unique Part Numbers", str(report.total_part_numbers))
    stats.add_row("Processing Time", f"{elapsed:.1f}s")
    stats.add_row("Output Directory", str(output_dir))
    
    console.print(stats)
    
    # Extraction method breakdown
    if report.extraction_breakdown:
        method_table = Table(
            title="Extraction Method Breakdown",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
        )
        method_table.add_column("Method", style="cyan")
        method_table.add_column("Pages", justify="right")
        
        for method, count in report.extraction_breakdown.items():
            method_table.add_row(method, str(count))
        
        console.print(method_table)
    
    # Chunk type breakdown
    if report.chunk_type_breakdown:
        chunk_table = Table(
            title="Chunk Type Breakdown",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold",
        )
        chunk_table.add_column("Type", style="cyan")
        chunk_table.add_column("Count", justify="right")
        
        for ctype, count in report.chunk_type_breakdown.items():
            chunk_table.add_row(ctype, str(count))
        
        console.print(chunk_table)
    
    # Flagged issues
    if report.flagged_issues:
        console.print(f"\n[yellow bold]Flagged Issues ({len(report.flagged_issues)}):[/yellow bold]")
        for issue in report.flagged_issues:
            console.print(f"  [yellow]  {issue}[/yellow]")
    
    if report.low_confidence_pages:
        console.print(
            f"\n[yellow]Low confidence pages:[/yellow] {report.low_confidence_pages}"
        )
    
    # Validation status
    if report.validation_passed:
        console.print("\n[green bold]  Validation PASSED[/green bold]")
    else:
        console.print("\n[red bold]  Validation FAILED — see flagged issues above[/red bold]")


def main():
    parser = argparse.ArgumentParser(
        prog="catalog2md",
        description="Convert technical PDF catalogs to RAG-optimized Markdown files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m catalog2md catalog.pdf -o ./output
  python -m catalog2md ./pdfs/ -o ./output --api-key sk-ant-...
  python -m catalog2md catalog.pdf -o ./output --force-method pdfplumber
  python -m catalog2md catalog.pdf -o ./output --min-tokens 256 --max-tokens 512
        """,
    )
    
    parser.add_argument(
        "input",
        type=Path,
        help="Path to a single PDF file or a directory of PDFs",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="Output directory for Markdown files and chunks",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Anthropic API key for Claude vision fallback (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--force-method",
        type=str,
        choices=["docling", "pdfplumber", "claude_vision"],
        default=None,
        help="Force a specific extraction method (skip fallback cascade)",
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=512,
        help="Minimum chunk size in tokens (default: 512)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Maximum chunk size in tokens for text chunks (default: 1024)",
    )
    parser.add_argument(
        "--no-docling",
        action="store_true",
        help="Skip Docling even if installed (use pdfplumber as primary)",
    )
    
    args = parser.parse_args()
    
    # Banner
    console.print(
        Panel(
            "[bold]catalog2md[/bold] — PDF Catalog to RAG-Optimized Markdown\n"
            f"Docling: {'[green]available[/green]' if DOCLING_AVAILABLE else '[yellow]not installed (using pdfplumber)[/yellow]'}\n"
            f"Claude Vision: {'[green]available[/green]' if (args.api_key or os.environ.get('ANTHROPIC_API_KEY')) else '[yellow]not configured[/yellow]'}",
            title="catalog2md v1.0.0",
            border_style="blue",
        )
    )
    
    # Validate input
    if not args.input.exists():
        console.print(f"[red]Input not found: {args.input}[/red]")
        sys.exit(1)
    
    # Find PDFs
    pdfs = find_pdfs(args.input)
    console.print(f"\nFound [bold]{len(pdfs)}[/bold] PDF(s) to process")
    
    # Set up extraction engine
    force = None
    if args.force_method:
        force = ExtractionMethod(args.force_method)
    
    orchestrator = ExtractionOrchestrator(
        use_docling=not args.no_docling,
        anthropic_api_key=args.api_key,
        force_method=force,
    )
    
    # Process each PDF
    args.output.mkdir(parents=True, exist_ok=True)
    
    for pdf_path in pdfs:
        try:
            process_single_pdf(
                pdf_path=pdf_path,
                output_dir=args.output,
                orchestrator=orchestrator,
                min_chunk_tokens=args.min_tokens,
                max_chunk_tokens=args.max_tokens,
            )
        except Exception as e:
            console.print(f"\n[red]Error processing {pdf_path.name}: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
    
    console.print(f"\n[bold green]Done.[/bold green] Output in: {args.output.resolve()}")


if __name__ == "__main__":
    main()
