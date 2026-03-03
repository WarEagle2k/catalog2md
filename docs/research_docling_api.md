# Docling Python Library — Production API Reference

**Library**: `docling` by IBM / DS4SD  
**Current version**: 2.75.0 (as of February 2026)  
**Sources**: [PyPI](https://pypi.org/project/docling/), [GitHub](https://github.com/DS4SD/docling), [Docling Docs](https://docling-project.github.io/docling/), [API Reference](https://docling-project.github.io/docling/reference/document_converter/)

---

## 1. Installation

### Basic install

```bash
pip install docling
```

**Requirements:**
- Python **3.10+** (Python 3.9 support was dropped in 2.70.0)
- Platforms: macOS, Linux, Windows (x86_64 and arm64)
- No mandatory system-level dependencies; optional OCR backends may require external binaries (see §7)

### Optional extras

```bash
pip install 'docling[easyocr]'       # EasyOCR engine (default engine, bundled)
pip install 'docling[tesserocr]'     # tesserocr Python bindings
pip install 'docling[ocrmac]'        # macOS Vision OCR (macOS only)
pip install 'docling[rapidocr]'      # RapidOCR engine
pip install 'docling[vlm]'           # Vision-Language Model pipeline (SmolDocling)
pip install 'docling[onnxruntime]'   # ONNX runtime acceleration
```

All optional extras as a flat list: `easyocr`, `tesserocr`, `ocrmac`, `vlm`, `rapidocr`, `onnxruntime`, `asr`, `xbrl`.

### Model artifacts / offline mode

On first run, Docling downloads model weights (~2–3 GB). For air-gapped environments:

```bash
# Pre-download to a local path
export DOCLING_ARTIFACTS_PATH="/local/path/to/models"
```

Or set programmatically via `PdfPipelineOptions(artifacts_path=...)` (see §7).

---

## 2. Core API — `DocumentConverter`

### Import path

```python
from docling.document_converter import DocumentConverter
```

### Minimal usage

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("path/to/document.pdf")  # local path or URL
print(result.document.export_to_markdown())
```

### `DocumentConverter` constructor signature

```python
DocumentConverter(
    allowed_formats: list[InputFormat] | None = None,
    format_options: dict[InputFormat, FormatOption] | None = None,
    # ...
)
```

- `allowed_formats`: Restrict which formats are accepted. Defaults to all supported formats.
- `format_options`: Per-format pipeline configuration (most important for PDF; see §7).

### `converter.convert()` method

```python
result = converter.convert(
    source,                       # str | Path | DocumentStream
    max_num_pages: int = ...,     # optional page limit
    max_file_size: int = ...,     # optional byte limit (e.g., 20971520 for 20 MB)
)
```

### `converter.convert_all()` method

Batch-convert multiple documents:

```python
results = converter.convert_all(
    sources: Iterable[str | Path | DocumentStream],
    raises_on_error: bool = True,
)
# Returns an Iterable[ConversionResult]
```

### `ConversionResult` fields

```python
result.document       # DoclingDocument — the main object
result.status         # ConversionStatus enum
result.errors         # list of errors
result.pages          # page-level intermediate data
result.input          # InputDocument (result.input.file.stem for filename)
result.timings        # performance timings
result.legacy_document  # deprecated legacy representation
result.assembled      # assembled intermediate representation
```

### `ConversionStatus` enum values

```
SUCCESS, PARTIAL_SUCCESS, FAILURE, PENDING, STARTED, SKIPPED
```

### Accepted `InputFormat` values

```
PDF, DOCX, PPTX, HTML, IMAGE, XLSX, MD, ASCIIDOC, CSV, 
JSON_DOCLING, XML_JATS, XML_USPTO
```

### Converting from binary streams

```python
from io import BytesIO
from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

buf = BytesIO(your_binary_pdf_bytes)
source = DocumentStream(name="my_doc.pdf", stream=buf)
converter = DocumentConverter()
result = converter.convert(source)
```

---

## 3. Markdown Export

### Primary method: `DoclingDocument.export_to_markdown()`

```python
result.document.export_to_markdown()  # returns str
```

**Full signature:**

```python
doc.export_to_markdown(
    delim: str = '\n\n',
    from_element: int = 0,
    to_element: int = maxsize,
    labels: Optional[set[DocItemLabel]] = None,
    strict_text: bool = False,
    escape_html: bool = True,
    escape_underscores: bool = True,
    image_placeholder: str = '<!-- image -->',
    enable_chart_tables: bool = True,
    image_mode: ImageRefMode = PLACEHOLDER,
    indent: int = 4,
    text_width: int = -1,
    page_no: Optional[int] = None,             # filter to a single page
    included_content_layers: Optional[set[ContentLayer]] = None,
    page_break_placeholder: Optional[str] = None,
    include_annotations: bool = True,
    mark_annotations: bool = False,
    compact_tables: bool = False,
    *,
    use_legacy_annotations: Optional[bool] = None,
    allowed_meta_names: Optional[set[str]] = None,
    blocked_meta_names: Optional[set[str]] = None,
    mark_meta: bool = False,
) -> str
```

**Key parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `page_no` | `None` | Export only content from this page number |
| `image_mode` | `PLACEHOLDER` | `PLACEHOLDER`, `EMBEDDED` (base64), or `REFERENCED` |
| `labels` | `None` | Only include items with these `DocItemLabel` values |
| `escape_underscores` | `True` | Escape underscores to avoid accidental italics |
| `strict_text` | `False` | Use original text (`orig`) instead of normalized text |
| `page_break_placeholder` | `None` | Insert a marker string at page boundaries |

### Save to file

```python
doc.save_as_markdown("output.md")
```

### Other export formats

```python
doc.export_to_html(page_no=None, ...)   # HTML string
doc.export_to_text(...)                  # plain text
doc.export_to_dict(...)                  # Python dict (for JSON)
doc.export_to_doctags(...)               # SmolDocling DocTags format
doc.save_as_json("output.json")          # lossless JSON (preserves page_no, bbox)
doc.save_as_html("output.html")
doc.save_as_yaml("output.yaml")
```

> **Critical note on lossiness**: `export_to_markdown()` is lossy — page numbers and bounding boxes are not preserved in the Markdown output. To retain full provenance (page_no, bbox), save as JSON and reload:
>
> ```python
> doc.save_as_json("doc.json")                          # lossless
> doc2 = DoclingDocument.load_from_json("doc.json")     # reload with full metadata
> ```

---

## 4. Table Extraction

### Accessing tables

```python
for table_ix, table in enumerate(result.document.tables):
    # table: TableItem
    print(f"Table {table_ix}: {table.data.num_rows} rows × {table.data.num_cols} cols")
```

`result.document.tables` is a `List[TableItem]`.

### `TableItem` — class overview

**Import**: `from docling_core.types.doc import TableItem`

```
TableItem (inherits FloatingItem)
├── data: TableData
├── label: Literal[TABLE, DOCUMENT_INDEX]
├── prov: List[ProvenanceItem]     # contains page_no and bbox
├── captions: List[RefItem]
├── footnotes: List[RefItem]
└── references: List[RefItem]
```

### `TableData` structure

```python
table.data.num_rows  # int — number of rows
table.data.num_cols  # int — number of columns
table.data.grid      # List[List[TableCell]] — 2D grid
table.data.table_cells  # List[AnyTableCell] — flat list of all cells
```

### `TableCell` fields

```python
cell.text                  # str — cell text content
cell.row_span              # int (default 1) — number of rows this cell spans
cell.col_span              # int (default 1) — number of columns this cell spans
cell.start_row_offset_idx  # int — starting row index in the grid
cell.end_row_offset_idx    # int — ending row index (inclusive)
cell.start_col_offset_idx  # int — starting column index
cell.end_col_offset_idx    # int — ending column index (inclusive)
cell.column_header         # bool — True if this cell is a column header
cell.row_header            # bool — True if this cell is a row header
cell.row_section           # bool — True if this cell is a row section label
cell.bbox                  # Optional[BoundingBox]
cell.fillable              # bool
```

### Iterating over merged/spanned cells

```python
for row_idx, row in enumerate(table.data.grid):
    for col_idx, cell in enumerate(row):
        if cell.row_span > 1 or cell.col_span > 1:
            print(
                f"Merged cell at [{row_idx}][{col_idx}]: "
                f"'{cell.text}' "
                f"spans rows {cell.start_row_offset_idx}–{cell.end_row_offset_idx}, "
                f"cols {cell.start_col_offset_idx}–{cell.end_col_offset_idx}"
            )
```

### `TableCellLabel` enum

```python
BODY           = 'body'
COLUMN_HEADER  = 'col_header'
ROW_HEADER     = 'row_header'
ROW_SECTION    = 'row_section'
```

### TableItem export methods

```python
# Export to Pandas DataFrame
df: pd.DataFrame = table.export_to_dataframe()

# Export to HTML (preserves rowspan/colspan attributes)
html: str = table.export_to_html(doc=result.document, add_caption=True)

# Export to Markdown
md: str = table.export_to_markdown()

# Export to OTSL (Object Token Sequence Language — model format)
otsl: str = table.export_to_otsl(
    doc=result.document,
    add_cell_location=True,
    add_cell_text=True,
    xsize=500,
    ysize=500,
)

# Export to document tokens format
table.export_to_document_tokens(
    doc=result.document,
    new_line="",
    xsize=500,
    ysize=500,
    add_location=True,
    add_cell_location=True,
    add_cell_text=True,
    add_caption=True,
)

# Get table image (requires generate_page_images=True in pipeline options)
img = table.get_image(doc=result.document)
```

### Complete table extraction example

```python
import pandas as pd
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("document.pdf")

for i, table in enumerate(result.document.tables):
    page_no = table.prov[0].page_no if table.prov else "unknown"
    print(f"\n--- Table {i} (page {page_no}) ---")
    print(f"  {table.data.num_rows} rows × {table.data.num_cols} cols")
    
    # Export as DataFrame
    df = table.export_to_dataframe()
    print(df.to_string())
    
    # Inspect cell-level span data
    for row in table.data.grid:
        for cell in row:
            if cell.row_span > 1 or cell.col_span > 1:
                print(f"  Merged: '{cell.text}' (row_span={cell.row_span}, col_span={cell.col_span})")
```

---

## 5. Page-Level Access

### ProvenanceItem — the core provenance object

Every `DocItem` (texts, tables, pictures, etc.) carries a `prov` list:

```python
item.prov            # List[ProvenanceItem]
item.prov[0].page_no  # int — 1-indexed page number
item.prov[0].bbox     # BoundingBox(l, t, r, b, coord_origin)
item.prov[0].charspan # Tuple[int, int] — character span within the page
```

`BoundingBox` fields:

```python
bbox.l   # float — left
bbox.t   # float — top
bbox.r   # float — right
bbox.b   # float — bottom
bbox.coord_origin  # CoordOrigin.BOTTOMLEFT or TOPLEFT
```

> **Note**: `prov` is populated reliably for PDF. For HTML, `prov` is not available (no paging concept). For DOCX, `prov` is empty because Word's paging is not stable.

### Accessing `doc.pages`

```python
doc.pages          # Dict[int, PageItem] — key is page_no (1-indexed)
doc.num_pages()    # int — total page count

page = doc.pages[1]
page.size          # Size(width, height) in points
page.image         # Optional[ImageRef] — page image if generated
```

### Filtering iteration by page

```python
# Iterate only items on page 2
for item, depth in result.document.iterate_items(page_no=2):
    print(f"  depth={depth}: [{item.label}] {getattr(item, 'text', '')[:80]}")
```

### Per-page Markdown export

```python
# Export only page 3 content as Markdown
page3_md = result.document.export_to_markdown(page_no=3)
```

### Per-page HTML export

```python
page3_html = result.document.export_to_html(page_no=3)
```

### `iterate_items()` — full signature

```python
doc.iterate_items(
    root: Optional[NodeItem] = None,          # start node (default: body)
    with_groups: bool = False,                 # include group nodes
    traverse_pictures: bool = False,           # recurse into picture sub-items
    page_no: Optional[int] = None,             # filter by page
    included_content_layers: set[ContentLayer] = DEFAULT_CONTENT_LAYERS,
    _level: int = 0,                           # internal depth tracker
) -> Iterable[Tuple[NodeItem, int]]            # yields (item, depth)
```

### Pattern: get page number for any item

```python
for item, _ in result.document.iterate_items():
    if item.prov:
        page = item.prov[0].page_no
        bbox = item.prov[0].bbox
        print(f"Page {page}: {getattr(item, 'text', '')[:60]}")
```

---

## 6. Chunking Support

Docling provides native chunkers that operate directly on `DoclingDocument`, preserving provenance metadata (page numbers, bounding boxes, headings).

> **Key recommendation**: Always chunk from `DoclingDocument` directly (or its lossless JSON). Chunking from an intermediate Markdown export loses page_no and bbox.

### Import paths

```python
from docling.chunking import HybridChunker           # recommended
from docling.chunking import HierarchicalChunker      # available via docling
from docling_core.transforms.chunker import HierarchicalChunker  # direct from core
```

For docling-core standalone usage:
```bash
pip install 'docling-core[chunking]'
# or with OpenAI tokenizer support:
pip install 'docling-core[chunking-openai]'
```

---

### `BaseChunker` — base class API

```python
def chunk(self, dl_doc: DoclingDocument, **kwargs) -> Iterator[BaseChunk]:
    """Returns chunks for the document."""

def contextualize(self, chunk: BaseChunk) -> str:
    """Returns metadata-enriched serialization (use this for embedding models)."""
```

> Note: `contextualize()` was previously called `serialize()` in older versions (pre-2.9.0). Both names may appear in community code examples. Prefer `contextualize()`.

---

### `HierarchicalChunker`

Creates **one chunk per detected document element**, respecting the document's structural hierarchy. By default, list items are merged into a single chunk.

```python
from docling_core.transforms.chunker import HierarchicalChunker

chunker = HierarchicalChunker(
    merge_list_items=True,           # default: True; set False to get one chunk per list item
    serializer_provider=None,        # optional custom serializer (e.g., Markdown table serializer)
)

for chunk in chunker.chunk(dl_doc=doc):
    print(chunk.text)
    print(chunk.meta.headings)        # List[str] — ancestor headings
    print(chunk.meta.captions)        # List[str] — figure/table captions
    print(chunk.meta.doc_items)       # List[DocItem] — source document items
    print(chunk.meta.origin)          # DocOrigin — filename, mimetype, binary_hash
```

---

### `HybridChunker`

Starts from hierarchical chunks and applies **tokenization-aware refinements**:
1. Splits oversized chunks that exceed `max_tokens`
2. Merges undersized peer chunks that share the same headings/captions (opt out via `merge_peers=False`)

```python
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

# Option A — default tokenizer (sentence-transformers/all-MiniLM-L6-v2)
chunker = HybridChunker()

# Option B — custom tokenizer aligned to your embedding model
EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained(EMBED_MODEL_ID),
    max_tokens=512,                     # optional, defaults from tokenizer config
)
chunker = HybridChunker(
    tokenizer=tokenizer,
    merge_peers=True,                   # default True
)

# Option C — pass model ID string directly
chunker = HybridChunker(tokenizer="BAAI/bge-small-en-v1.5", max_tokens=512)

chunk_iter = chunker.chunk(dl_doc=doc)

for chunk in chunk_iter:
    raw_text = chunk.text                           # plain chunk text
    enriched_text = chunker.contextualize(chunk)    # includes section headings — use for embedding
```

---

### `DocChunk` — chunk data model

Each chunk returned by the chunkers is a `DocChunk` (subclass of `BaseChunk`) with:

```python
chunk.text               # str — plain text of the chunk
chunk.meta               # DocMeta — metadata object

# DocMeta fields:
chunk.meta.doc_items     # List[DocItem] — source document elements
chunk.meta.headings      # List[str] — ancestor section headings (outermost first)
chunk.meta.captions      # List[str] — associated figure/table captions
chunk.meta.origin        # DocOrigin — source document info
chunk.meta.origin.filename    # str — source filename
chunk.meta.origin.mimetype    # str — e.g., 'application/pdf'
chunk.meta.origin.binary_hash # int — file hash
```

### Accessing page numbers from chunks

```python
page_numbers = sorted(set(
    prov.page_no
    for item in chunk.meta.doc_items
    for prov in item.prov
    if hasattr(prov, "page_no")
))
```

### DocMeta JSON representation

```json
{
  "schema_name": "docling_core.transforms.chunker.DocMeta",
  "version": "1.0.0",
  "doc_items": [
    {
      "self_ref": "#/texts/50",
      "label": "text",
      "prov": [
        {
          "page_no": 3,
          "bbox": {"l": 108.0, "t": 405.14, "r": 504.0, "b": 330.78, "coord_origin": "BOTTOMLEFT"},
          "charspan": [0, 608]
        }
      ]
    }
  ],
  "headings": ["3.2 AI models"],
  "origin": {
    "mimetype": "application/pdf",
    "binary_hash": 11465328351749295394,
    "filename": "2408.09869v5.pdf"
  }
}
```

### Complete chunking with page numbers example

```python
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

doc = DocumentConverter().convert("document.pdf").document
chunker = HybridChunker()

for i, chunk in enumerate(chunker.chunk(dl_doc=doc)):
    page_numbers = sorted(set(
        prov.page_no
        for item in chunk.meta.doc_items
        for prov in item.prov
        if hasattr(prov, "page_no")
    ))
    section = " / ".join(chunk.meta.headings) if chunk.meta.headings else "(no heading)"
    embed_text = chunker.contextualize(chunk)  # includes heading context
    
    print(f"Chunk {i}: pages={page_numbers}, section='{section}'")
    print(f"  text[:100]: {chunk.text[:100]!r}")
```

---

## 7. Configuration Options

### `PdfPipelineOptions` — full reference

**Import**: `from docling.datamodel.pipeline_options import PdfPipelineOptions`

```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption

pipeline_options = PdfPipelineOptions(
    # Model artifacts
    artifacts_path=None,           # Optional[Union[Path, str]] — local model path

    # OCR
    do_ocr=True,                   # bool — enable OCR (default True)
    ocr_options=EasyOcrOptions(),  # OCR engine config (see below)

    # Table structure recognition
    do_table_structure=True,       # bool — run TableFormer model (default True)
    table_structure_options=TableStructureOptions(),  # see below

    # Enrichment (off by default)
    do_code_enrichment=False,
    do_formula_enrichment=False,
    do_picture_classification=False,
    do_picture_description=False,

    # Image generation (required for .get_image() calls)
    generate_page_images=False,
    generate_picture_images=False,
    images_scale=1.0,              # float — scale factor for generated images

    # Other
    force_backend_text=False,      # Use only backend-extracted text (no OCR)
    enable_remote_services=False,  # Opt-in for remote API services (e.g., picture description)
    document_timeout=None,         # Optional[float] — per-document timeout in seconds
    create_legacy_output=True,     # Include legacy_document in result
)

doc_converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)
```

### `TableStructureOptions`

```python
from docling.datamodel.pipeline_options import TableStructureOptions, TableFormerMode

pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE  # or FAST (default)
pipeline_options.table_structure_options.do_cell_matching = True          # default True
```

| Option | Values | Description |
|--------|--------|-------------|
| `mode` | `FAST` (default), `ACCURATE` | Model quality vs. speed tradeoff. ACCURATE uses a higher-quality TableFormer model. |
| `do_cell_matching` | `True` (default), `False` | Match text cells from PDF to predicted structure. Set `False` to use only model-predicted cells. |

### OCR Options

#### `EasyOcrOptions` (default)

```python
from docling.datamodel.pipeline_options import EasyOcrOptions

EasyOcrOptions(
    lang=['fr', 'de', 'es', 'en'],      # list of language codes
    confidence_threshold=0.5,            # float — filter low-confidence OCR results
    use_gpu=None,                        # Optional[bool] — auto-detect GPU if None
    download_enabled=True,               # bool — allow model download
    force_full_page_ocr=False,           # bool — OCR entire page (not just non-text regions)
    bitmap_area_threshold=0.05,          # float — minimum bitmap area fraction to trigger OCR
    model_storage_directory=None,        # Optional[str] — custom model cache path
    recog_network='standard',            # Optional[str]
)
```

Install: included in base `pip install docling` (EasyOCR bundled).

#### `TesseractCliOcrOptions` (Tesseract via CLI)

```python
from docling.datamodel.pipeline_options import TesseractCliOcrOptions

TesseractCliOcrOptions(
    lang=['fra', 'deu', 'spa', 'eng'],   # Tesseract 3-letter ISO codes
    tesseract_cmd='tesseract',
    path=None,                           # Optional[str] — path to tesseract binary
    force_full_page_ocr=False,
    bitmap_area_threshold=0.05,
)
```

Install: `pip install 'docling[tesserocr]'`; requires `tesseract` binary on PATH.

#### `TesseractOcrOptions` (tesserocr Python binding)

```python
from docling.datamodel.pipeline_options import TesseractOcrOptions
```

#### `OcrMacOptions` (macOS Vision framework)

```python
from docling.datamodel.pipeline_options import OcrMacOptions

OcrMacOptions(
    lang=['fr-FR', 'de-DE', 'es-ES', 'en-US'],
    framework='vision',
    recognition='accurate',              # or 'fast'
)
```

Install: `pip install 'docling[ocrmac]'`; macOS only.

#### `RapidOcrOptions`

```python
from docling.datamodel.pipeline_options import RapidOcrOptions

RapidOcrOptions(
    lang=['english', 'chinese'],
    text_score=0.5,                      # confidence threshold
    use_gpu=None,
)
```

Install: `pip install 'docling[rapidocr]'`

### `AcceleratorOptions`

```python
from docling.datamodel.pipeline_options import AcceleratorOptions

pipeline_options.accelerator_options = AcceleratorOptions(
    device='auto',                       # 'auto', 'cpu', 'cuda', 'mps', or AcceleratorDevice enum
    num_threads=4,                       # int — CPU thread count (also reads OMP_NUM_THREADS env var)
    cuda_use_flash_attention2=False,     # bool — Flash Attention 2 on CUDA
)
```

### Environment variables

| Variable | Effect |
|----------|--------|
| `DOCLING_ARTIFACTS_PATH` | Path to pre-downloaded model artifacts (overrides `artifacts_path`) |
| `OMP_NUM_THREADS` | CPU thread count (default: 4) |

### Common configuration patterns

```python
# Pattern A: High-accuracy table extraction
pipeline_options = PdfPipelineOptions(do_table_structure=True)
pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE

# Pattern B: Disable OCR (fast, native-text PDFs only)
pipeline_options = PdfPipelineOptions(do_ocr=False)

# Pattern C: Full OCR on all pages (e.g., scanned PDFs)
pipeline_options = PdfPipelineOptions(
    do_ocr=True,
    ocr_options=EasyOcrOptions(force_full_page_ocr=True),
)

# Pattern D: Generate page images for bounding box visualization
pipeline_options = PdfPipelineOptions(
    generate_page_images=True,
    generate_picture_images=True,
    images_scale=2.0,
)

# Pattern E: Offline/air-gapped
pipeline_options = PdfPipelineOptions(artifacts_path="/models/docling")
```

---

## 8. Document Structure — `DoclingDocument` Model

### Import

```python
from docling_core.types.doc import DoclingDocument
```

### Top-level structure

`DoclingDocument` is a **Pydantic** model with the following top-level containers:

```
DoclingDocument
├── body: NodeItem                     # Root of main content tree; children order = reading order
├── furniture: NodeItem                # Root of non-body tree (headers, footers, page numbers)
├── groups: List[GroupItem]            # Named containers (chapters, list groups, etc.)
│
├── texts: List[Union[SectionHeaderItem, ListItem, TextItem, CodeItem]]
├── tables: List[TableItem]
├── pictures: List[PictureItem]
├── key_value_items: List[KeyValueItem]
│
├── pages: Dict[int, PageItem]         # page_no → PageItem
└── version: str                       # DoclingDocument schema version
```

### Document item class hierarchy

```
NodeItem
└── DocItem                            # abstract base for content items
    ├── TextItem                       # paragraphs, titles, captions, footnotes, etc.
    │   └── SectionHeaderItem          # section headings (adds: level: LevelNumber)
    │   └── ListItem                   # list entries
    │   └── CodeItem                   # code blocks
    ├── FloatingItem                   # base for floating/anchored items
    │   ├── TableItem                  # tables (adds: data: TableData)
    │   ├── PictureItem                # images (adds: annotations: List[PictureDataType])
    │   └── KeyValueItem               # key-value regions (adds: graph: GraphData)
    └── GroupItem                      # structural container (not content itself)
```

### Common `DocItem` fields (all subclasses)

```python
item.self_ref    # str — JSON pointer, e.g., "#/texts/3"
item.label       # DocItemLabel enum value
item.prov        # List[ProvenanceItem] — page_no, bbox, charspan
item.parent      # Optional[RefItem] — parent node reference
item.children    # List[RefItem] — child node references
item.content_layer  # ContentLayer (BODY, FURNITURE, etc.)
```

### `DocItemLabel` enum — all values

```python
CAPTION            = 'caption'
CHECKBOX_SELECTED  = 'checkbox_selected'
CHECKBOX_UNSELECTED = 'checkbox_unselected'
CODE               = 'code'
DOCUMENT_INDEX     = 'document_index'
FOOTNOTE           = 'footnote'
FORM               = 'form'
FORMULA            = 'formula'
KEY_VALUE_REGION   = 'key_value_region'
LIST_ITEM          = 'list_item'
PAGE_FOOTER        = 'page_footer'
PAGE_HEADER        = 'page_header'
PARAGRAPH          = 'paragraph'
PICTURE            = 'picture'
REFERENCE          = 'reference'
SECTION_HEADER     = 'section_header'
TABLE              = 'table'
TEXT               = 'text'
TITLE              = 'title'
```

### `TextItem` fields

```python
item.text    # str — normalized text
item.orig    # str — original (un-normalized) text
item.label   # one of: CAPTION, CHECKBOX_SELECTED, CHECKBOX_UNSELECTED, FOOTNOTE,
             #         FORMULA, PAGE_FOOTER, PAGE_HEADER, PARAGRAPH, REFERENCE,
             #         TEXT, TITLE
```

### `SectionHeaderItem` fields (extends `TextItem`)

```python
item.label  # Literal[SECTION_HEADER]
item.level  # LevelNumber — heading level (1 = top level, 2 = subsection, etc.)
item.text   # str — heading text
```

### Tree traversal with `iterate_items()`

```python
for item, depth in result.document.iterate_items():
    label = item.label
    text = getattr(item, 'text', None)
    page = item.prov[0].page_no if item.prov else None
    print(f"{'  ' * depth}[{label}] (p.{page}) {text[:60] if text else ''}")
```

### Reading order

Reading order is encoded in the `body` tree: items appear in the order they were detected on each page, following the document's logical flow. `body.children` lists top-level elements; nested groups (e.g., list containers, section groups) have their own `children`.

### Full traversal example

```python
from docling.document_converter import DocumentConverter
from docling_core.types.doc import DocItemLabel

result = DocumentConverter().convert("document.pdf")
doc = result.document

print(f"Pages: {doc.num_pages()}")
print(f"Text items: {len(doc.texts)}")
print(f"Tables: {len(doc.tables)}")
print(f"Pictures: {len(doc.pictures)}")

# Traverse all items with hierarchy
for item, depth in doc.iterate_items(with_groups=False):
    indent = "  " * depth
    page = item.prov[0].page_no if item.prov else "?"
    
    if item.label == DocItemLabel.SECTION_HEADER:
        print(f"{indent}[H{item.level}] p.{page}: {item.text}")
    elif item.label == DocItemLabel.PARAGRAPH:
        print(f"{indent}[P] p.{page}: {item.text[:80]}...")
    elif item.label == DocItemLabel.TABLE:
        print(f"{indent}[TABLE] p.{page}: {item.data.num_rows}×{item.data.num_cols}")
    elif item.label == DocItemLabel.TITLE:
        print(f"{indent}[TITLE] p.{page}: {item.text}")
```

### Filter document to specific pages

```python
# Get a sub-document containing only pages 2 and 3
sub_doc = doc.filter(page_nrs={2, 3})
```

---

## 9. Framework Integrations

Docling integrates natively with major gen AI frameworks via `BaseChunker`:

```python
# LlamaIndex
from llama_index.node_parser.docling import DoclingNodeParser
from docling.chunking import HybridChunker

node_parser = DoclingNodeParser(chunker=HybridChunker())

# LangChain
from langchain_docling import DoclingLoader
from docling.chunking import HybridChunker

loader = DoclingLoader(file_path="doc.pdf", chunker=HybridChunker())
docs = loader.load()

# Haystack
# See: https://docling-project.github.io/docling/examples/rag_haystack/
```

---

## 10. Known Limitations & Gotchas

| Issue | Detail |
|-------|--------|
| **Markdown is lossy** | `export_to_markdown()` drops `prov` (page_no, bbox). Use `save_as_json()` + `load_from_json()` to preserve all metadata. |
| **DOCX prov is empty** | `prov` fields are not populated for DOCX files (Word pagination is not stable). Only PDF guarantees `prov`. |
| **HTML has no prov** | HTML has no native page concept; `prov` is unavailable for HTML inputs. |
| **Heading levels in PDF** | PDF section header levels are not always reliably detected. DOCX, HTML, and PPTX provide reliable heading hierarchy natively. |
| **EasyOCR false-alarm warning** | `HybridChunker` may trigger a transformers "sequence length" warning — this is a known false alarm and does not affect output. |
| **generate_page_images required for image methods** | Calling `table.get_image()` or `picture.get_image()` requires `PdfPipelineOptions(generate_page_images=True)`. |
| **Model download on first run** | ~2–3 GB of model weights are downloaded on first use. Use `artifacts_path` or `DOCLING_ARTIFACTS_PATH` to cache. |

---

## 11. Quick Reference — Import Map

```python
# Core converter
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
    WordFormatOption,
    ImageFormatOption,
    # etc.
)

# Data models
from docling.datamodel.base_models import (
    InputFormat,
    DocumentStream,
    ConversionStatus,
)

# Pipeline options
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
    EasyOcrOptions,
    TesseractCliOcrOptions,
    TesseractOcrOptions,
    OcrMacOptions,
    RapidOcrOptions,
    AcceleratorOptions,
    AcceleratorDevice,
)

# Document types (from docling-core)
from docling_core.types.doc import (
    DoclingDocument,
    DocItem,
    TextItem,
    SectionHeaderItem,
    TableItem,
    TableData,
    TableCell,
    PictureItem,
    KeyValueItem,
    NodeItem,
    ProvenanceItem,
    BoundingBox,
    DocItemLabel,
    PageItem,
)

# Chunking
from docling.chunking import (
    HybridChunker,
    HierarchicalChunker,
    BaseChunker,
    DocChunk,
)
# or from docling-core directly:
from docling_core.transforms.chunker import HierarchicalChunker
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
```
