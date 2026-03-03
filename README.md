# catalog2md

**PDF Catalog → RAG-Optimized Markdown**

Convert industrial/technical PDF catalogs into clean, chunked Markdown optimized for retrieval-augmented generation (RAG) pipelines.

## Features

- **Docling** as primary extraction engine (ML-based table structure recognition, layout understanding)
- **pdfplumber** fallback for pages where Docling struggles
- Preserves all specification tables as Markdown tables with fully descriptive headers
- Detects and preserves industrial part numbers (never split or truncated)
- Table-aware chunking (512–1024 tokens, tables never split)
- YAML frontmatter on each chunk with metadata
- Validation report for every conversion

## Quick Start

### 1. Install dependencies

```bash
pip install docling pdfplumber pyyaml rich tiktoken pypdf --break-system-packages
# For CPU-only PyTorch (smaller install):
pip install torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages
```

### 2. Web Interface (recommended)

```bash
python run_web.py
```

Open **http://localhost:8080** in your browser. Upload a PDF, get results.

### 3. Command Line

```bash
# Convert a single PDF
python -m catalog2md catalog.pdf --output ./output

# Convert a directory of PDFs
python -m catalog2md ./pdf_folder/ --output ./output
```

## Web Interface

The web interface provides:
- Drag-and-drop PDF upload
- Real-time progress indicator
- Overview dashboard (pages, chunks, tables, part numbers, validation status)
- Consolidated Markdown viewer with copy/download
- Individual chunk browser with filtering and export

Run locally with `python run_web.py` — no external services, no API keys, no timeouts.

## CLI Options

```
python -m catalog2md <input> [options]

Arguments:
  input                  PDF file or directory

Options:
  --output DIR           Output directory (default: ./catalog2md_output)
  --no-docling           Skip Docling, use pdfplumber only
  --force-method METHOD  Force extraction method: docling, pdfplumber, or claude_vision
  --api-key KEY          Anthropic API key for Claude vision fallback
  --min-tokens N         Minimum chunk size in tokens (default: 512)
  --max-tokens N         Maximum chunk size in tokens (default: 1024)
```

## Output Structure

```
output/
├── catalog_name/
│   ├── catalog_name.md           # Consolidated Markdown
│   └── chunks/
│       ├── chunk_001.md          # Individual chunks with YAML frontmatter
│       ├── chunk_002.md
│       └── ...
```

## Architecture

1. **Extraction**: Docling (primary) → pdfplumber (fallback) → Claude Vision (final fallback, requires API key)
2. **Table Processing**: Parse tables, flatten merged/spanned headers, validate column consistency
3. **Part Number Detection**: Regex patterns for industrial part numbers preserved as critical data
4. **Chunking**: Text chunks target 512–1024 tokens; tables are atomic (never split)
5. **Validation**: Column consistency, part number completeness, chunk size bounds
