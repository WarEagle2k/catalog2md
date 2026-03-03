# RAG Chunking Best Practices for Technical PDF Documents
**Research Report — February 27, 2026**

---

## Executive Summary

Effective chunking is one of the highest-leverage decisions in a RAG pipeline. Poor chunking can degrade retrieval accuracy far more than switching embedding models. This report synthesizes current research (2024–2026) from academic papers, framework maintainers (Docling/IBM, LlamaIndex, LangChain, Unstructured.io), and practitioner benchmarks across seven areas relevant to technical PDF catalogs.

**Key findings at a glance:**

| Topic | Recommended Approach |
|-------|---------------------|
| Table handling | Atomic per-table chunks; repeat headers for row-level splits |
| Chunk size | 512–1024 tokens for technical docs; 256–512 for fact lookups |
| Overlap | 10–20% of chunk size (avoid < 5% or > 25%) |
| Context preservation | Breadcrumb path prepend + Anthropic-style contextual enrichment |
| Metadata schema | source, doc_id, section_path, page_number, chunk_id, content_type |
| Token counting | tiktoken (cl100k_base) for accuracy; ~1.3 tokens/word as fast heuristic |
| Part numbers | Boundary-protected regex + metadata extraction |
| Docling chunker | HybridChunker preferred over HierarchicalChunker for RAG/vector indexes |

---

## 1. Table-Aware Chunking

### The Core Problem

Standard text chunking treats tables as flat strings, breaking row-column relationships and losing header context. According to a [February 2026 paper in the Emerging Science Journal](https://www.ijournalse.org/index.php/ESJ/article/view/3380), structure-aware table chunking achieves the highest answer accuracy (0.73) versus baselines using naive text-centric approaches.

### Recommended Strategies

**1a. Atomic Table Chunks (Small Tables)**

For tables that fit within your token limit, keep the entire table as a single indivisible chunk. Research published on [arXiv in July 2025](https://arxiv.org/pdf/2507.12425) confirms: "Storing Entire Tables as Chunks: Effective for small tables." This preserves row-column relationships and semantic coherence.

**1b. Row-Level Indexing (Large Tables)**

For large tables, index each row separately — but **always repeat the full column headers** in each row-chunk. The [arXiv multimodal chunking paper (June 2025)](https://arxiv.org/html/2506.16035v2) explicitly states as a critical rule: "Each table row becomes a separate chunk while preserving headers for context."

Example chunk structure for row-level indexing:
```
Table: Product Specifications — Air Handlers
| Model | CFM | Static Pressure | Weight |
| AH-350 | 3500 | 0.5 in WG | 145 lbs |
```

**1c. Table Caption and Title Preservation**

Always include the table title (typically the paragraph immediately preceding the table) and any caption. According to [Sarthakai AI's layout-aware chunking guide](https://sarthakai.substack.com/p/improve-your-rag-accuracy-with-a):
> "Include column headers with every chunk. Add the table title (usually the sentence or paragraph right before the table)."

**1d. JSON/CSV Serialization for Structured Tables**

For specification tables with complex structure, consider serializing to JSON or Markdown rather than plain text. The [arXiv July 2025 enterprise RAG framework paper](https://arxiv.org/pdf/2507.12425) uses Camelot and Azure Document Intelligence to extract tables into structured JSON with metadata. Docling's `HybridChunker` supports Markdown serializers for tables, which help generative models understand structure.

**1e. Detection and Separation Pipeline**

The recommended pipeline for technical PDFs:
1. Use a structure-aware parser (Docling, Unstructured.io, Azure DI) to detect table boundaries
2. Extract tables as separate document elements before chunking
3. Apply rule: if table fits in token limit → atomic chunk; if oversized → row-level split with header repetition
4. Store `content_type: "table"` in metadata for retrieval-time filtering

### What NOT to Do

- Never let fixed-size text splitters cut through table rows mid-line
- Never treat tables as plain paragraphs without header preservation
- Avoid chunking across table boundaries (end of one table / start of another in same chunk)

---

## 2. Optimal Chunk Sizes

### Benchmark Evidence

| Source | Optimal Range | Context |
|--------|--------------|---------|
| [NVIDIA benchmark (June 2025)](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/) | Page-level wins (0.648 acc); 512–1024 tokens for token-based | Across 5 diverse datasets |
| [Unstructured.io best practices](https://unstructured.io/blog/chunking-for-rag-best-practices) | ~250 tokens starting point | General recommendation |
| [Ailog 2025 guide](https://app.ailog.fr/en/blog/guides/chunking-strategies) | 512–1024 tokens for technical docs | Technical documentation specifically |
| [Firecrawl 2026 guide](https://www.firecrawl.dev/blog/best-chunking-strategies-rag) | 400–512 tokens default; 1024+ for analytical | Query-type dependent |
| [MDPI Bioengineering Nov 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12649634/) | Adaptive chunking: 87% vs 13% fixed baseline | Clinical decision support |
| [Chroma research](https://research.trychroma.com/evaluating-chunking) | 200–400 tokens for highest precision | Academic benchmarking |

### Practical Size Guidelines

```
Use Case                    Chunk Size    Overlap
─────────────────────────────────────────────
Fact lookups (part nums)    256–512 tok   10–15%
Technical specs/catalogs    512–1024 tok  15–20%
Analytical / context-heavy  1024–2048 tok 10–15%
Code snippets               256–512 tok   10–20%
Tables (row-level)          Variable      0% (headers repeated)
Short FAQ / definitions     128–256 tok   0–10%
```

**Key insight from NVIDIA's study:** "Page-level chunking achieved the highest average accuracy (0.648) across all datasets and the lowest standard deviation (0.107)." For paginated technical PDFs, page-level chunking is a strong baseline before fine-tuning.

### Embedding Model Token Limits (2025)

Different embedding models have different hard limits:

| Model | Max Tokens | Notes |
|-------|-----------|-------|
| OpenAI text-embedding-3-small/large | 8,191 | Allows large chunks; precision suffers at max |
| sentence-transformers/all-MiniLM-L6-v2 | 512 | Common open-source; chunk must stay under limit |
| sentence-transformers/all-mpnet-base-v2 | 514 | Similar constraint |
| Voyage voyage-3-large | 32,000 | Long context; supports late chunking |
| Voyage voyage-context-3 | 32,000 | Contextualized embeddings (see §3) |
| Cohere embed-v3 | 512 | Typical production model |

**Rule of thumb:** Always configure your chunker's `max_tokens` to the embedding model's limit. As [Docling's hybrid chunking docs](https://docling-project.github.io/docling/examples/hybrid_chunking/) state: "In a RAG / retrieval context, it is important to make sure that the chunker and embedding model are using the same tokenizer."

### The "Sweet Spot" Principle

[NVIDIA's experiments](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/) found that "very small (128 tokens) and very large (2,048 tokens) chunks generally underperformed medium-sized chunks." The pattern holds across datasets:
- **128 tokens**: Too granular, loses context, poor embedding quality
- **2048 tokens**: Too broad, dilutes semantic signals, drops precision
- **512–1024 tokens**: Consistent sweet spot across diverse document types

---

## 3. Context Preservation Techniques

### 3a. Breadcrumb Path Prepending

The single most impactful low-cost technique. Build an abstract syntax tree from the document hierarchy and prepend it to every chunk:

```
// Example from ByteVagabond enterprise RAG case study
const contextPath = "Product Catalog > Air Handlers > Installation > Wiring";
const chunkWithContext = `${contextPath}\n\n${chunkContent}`;
```

Source: [ByteVagabond enterprise RAG (1200+ hours)](https://bytevagabond.com/post/how-to-build-enterprise-ai-rag/) — "Document-based chunking with context preservation beats simple fixed-size chunking."

**Implementation notes:**
- Keep breadcrumb path to ~20–50 tokens; truncate from left if path is too long
- Include document title, section path, subsection at minimum
- For folder-structured document sets, include folder/file path as the outermost level
- Prepend to the text that gets embedded (not necessarily to the stored text — see §4)

### 3b. Anthropic Contextual Retrieval

[Anthropic's September 2024 "Contextual Retrieval" technique](https://www.anthropic.com/news/contextual-retrieval) uses an LLM to generate 50–100 token "situating context" prepended to each chunk before embedding. Results:
- **35% reduction** in top-20 retrieval failure rate with contextual embeddings alone
- **49% reduction** when combined with hybrid BM25+embedding search
- **67% reduction** with full contextual retrieval + reranking

The prompt used:
```
<document>{{WHOLE_DOCUMENT}}</document>

Here is the chunk we want to situate within the whole document:
<chunk>{{CHUNK_CONTENT}}</chunk>

Please give a short succinct context to situate this chunk within the overall 
document for the purposes of improving search retrieval of the chunk. 
Answer only with the succinct context and nothing else.
```

Cost note: ~$1.02 per million document tokens using Claude 3 Haiku with prompt caching. The document gets cached once; each chunk call only pays for the small incremental tokens.

**Practical approach for technical catalogs:** Even without LLM-generated context, a deterministic rule-based approach achieves most of the benefit — include the document title, section header path, and table caption in the text sent for embedding.

### 3c. Parent-Child (Small-to-Large) Retrieval

Index small "child" chunks for precise retrieval, but return larger "parent" chunks to the LLM for generation context:

```python
# LangChain ParentDocumentRetriever pattern
parent_splitter = RecursiveCharacterTextSplitter(chunk_size=1000)
child_splitter = RecursiveCharacterTextSplitter(chunk_size=200)
retriever = ParentDocumentRetriever(
    vectorstore=vectorstore,
    docstore=store,
    child_splitter=child_splitter,
    parent_splitter=parent_splitter,
)
```

Source: [LangCopilot RAG chunking guide](https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide) — "Give you the best of both worlds: precision and context."

LlamaIndex's `HierarchicalNodeParser` provides a similar multi-level hierarchy (`chunk_sizes=[2048, 512, 128]`).

### 3d. Late Chunking (Advanced)

Late chunking embeds the entire document first (if model context allows), then creates chunk vectors by mean-pooling token embeddings over chunk boundaries. This means every chunk's embedding has full-document context.

- Works best with long-context models like Voyage voyage-3-large
- [Firecrawl 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag): "Retrieval improved across all boundary strategies when paired with late chunking"
- Not a replacement for other strategies — acts as a layer on top

### 3e. Section Headers as Chunk Boundaries

For hierarchically structured technical documents, always treat heading levels (H1/H2/H3) as hard chunk boundaries. Never split a chunk across a section heading. From [Dell Technologies' chunking guide](https://infohub.delltechnologies.com/es-es/p/chunk-twice-retrieve-once-rag-chunking-strategies-optimized-for-different-content-types/):
> "Your chunking strategy must preserve these relationships while keeping code examples intact and maintaining the breadcrumb trail of section headers that provide essential context."

---

## 4. YAML Front-Matter for Chunk Files

When chunks are stored as individual files (e.g., for git-based knowledge bases or disk-based indexing), YAML front-matter provides a standardized metadata envelope.

### Recommended Schema

```yaml
---
# Source Attribution
source_file: "AH-Series_Installation_Manual_v3.2.pdf"
doc_id: "ah-series-install-v32"
doc_title: "Air Handler Series — Installation Manual"
doc_version: "3.2"
doc_date: "2025-08-15"

# Structural Location
section_path: "Electrical > Wiring Connections > Low-Voltage Control"
section_heading: "Low-Voltage Control Wiring"
parent_section: "Wiring Connections"
page_number: 47
page_range: "47-48"

# Chunk Identity
chunk_id: "ah-series-install-v32-p47-c03"
chunk_index: 3            # position within document
total_chunks: 142         # total chunks from this document
chunk_type: "text"        # text | table | code | figure_caption | list

# Content Classification  
content_type: "procedure"  # procedure | specification | warning | overview
product_line: "Air Handler"
model_scope: ["AH-350", "AH-500", "AH-750"]   # models this chunk applies to
part_numbers: ["12345-001", "12345-002"]        # extracted part numbers

# Retrieval Hints
keywords: ["low-voltage", "24VAC", "thermostat wire", "R terminal"]
is_table: false
is_procedure: true

# Embedding Info
embed_model: "text-embedding-3-small"
token_count: 487
chunk_overlap_prev: 50    # tokens shared with preceding chunk
chunk_overlap_next: 50

# Processing
created_at: "2026-02-27T13:46:00Z"
chunker: "HybridChunker"
chunker_version: "2.9.0"
---
```

### Metadata Field Guidance

**Always include:**
- `source_file` / `doc_id`: Essential for attribution and deduplication
- `section_path`: Full breadcrumb path (enables filtering by section)
- `page_number`: For PDF citation and human verification
- `chunk_id`: Unique stable identifier (use hash or structured ID)
- `content_type`: Enables type-specific retrieval strategies

**Include when available:**
- `model_scope` / `part_numbers`: Enables metadata-filtered retrieval for part-specific queries (see §6)
- `chunk_type: "table"`: Signal for special rendering in responses
- `token_count`: For monitoring and debugging chunk size distribution

**Metadata storage pattern:** Store metadata separately from the embedding text. Embed only the textual content (optionally enriched with breadcrumb context). As noted in [Docling's GitHub discussion](https://github.com/docling-project/docling/discussions/191): "You should embed only the actual text content and store the metadata alongside it so you can filter or rank."

### Vector Database Metadata Filtering

Metadata fields become filterable attributes in vector databases:
```python
# Example: retrieve only table chunks for a specific model
results = vector_store.similarity_search(
    query="wiring specifications",
    filter={"chunk_type": "table", "model_scope": {"$contains": "AH-350"}}
)
```

---

## 5. Token Counting Approaches

### 5a. tiktoken (Recommended for Production)

`tiktoken` is OpenAI's tokenizer, open-sourced and widely adopted as the standard for accurate token counting. It's model-specific, which matters because different models tokenize differently.

```python
import tiktoken

# cl100k_base: used by gpt-4, gpt-3.5-turbo, text-embedding-3-*
encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(encoder.encode(text))

# For model-specific counting:
encoder = tiktoken.encoding_for_model("text-embedding-3-small")
```

**Why cl100k_base?** It's the base encoding for OpenAI embeddings and GPT-4 family models. For Anthropic Claude, the tokenization is similar enough that cl100k_base estimates are acceptable. For HuggingFace models, use the model's own tokenizer (see §5b).

Common use case pattern from production ([DEV Community guide](https://dev.to/aairom/the-secret-to-efficient-rag-a-step-by-step-guide-to-chunking-and-counting-your-vectors-25go)):
```python
TOKENIZER = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(TOKENIZER.encode(text))

# Use as length_function in LangChain splitters:
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=50,
    length_function=count_tokens,  # token-accurate sizing
)
```

### 5b. HuggingFace Tokenizers (For HF Models)

For sentence-transformers models, use the model's own tokenizer:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

def count_tokens_hf(text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))
```

Docling's `HybridChunker` accepts a `HuggingFaceTokenizer` wrapper that does this automatically:
```python
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2"),
    max_tokens=512,
)
```

### 5c. Fast Heuristics (For Pre-screening)

When exact counting is too slow (e.g., real-time filtering), use these heuristics:

| Heuristic | Rule | Accuracy |
|-----------|------|----------|
| Word-based | `tokens ≈ words × 1.3` | ±10–15% |
| Character-based | `tokens ≈ chars / 4` | ±15–20% |
| Firecrawl estimate | ~1.3 tokens/word | Commonly cited |

From [Firecrawl's 2026 guide](https://www.firecrawl.dev/blog/best-chunking-strategies-rag): "100 documents × 5,000 words each = 500,000 words. At ~1.3 tokens/word = 650,000 tokens."

**Recommendation:** Use the 1.3 multiplier for budget estimation and quick pre-screening. Use tiktoken for actual chunk boundary decisions. For performance-critical pipelines, the [Shelby Jenkins text segmentation analysis](https://shelbyjenkins.github.io/blog/text-segmentation-1/) shows token count can be *estimated* per split piece to minimize tokenizer calls: "An estimated token count allows us to call the tokenizer minimally: when a split is created and when a chunk is finalized."

### 5d. Counting Metadata Overhead

A critical and often-overlooked point: when sizing chunks, count the **total tokens sent to the embedding model**, including prepended headers/breadcrumbs. If your section path adds 30 tokens and your chunk body is 490 tokens, the actual embedded text is 520 tokens — which may exceed a 512-token model limit.

From [Docling's GitHub discussion](https://github.com/docling-project/docling/discussions/191): "An important point is whether relevant metadata (e.g. headings) are indeed considered when calculating the token limits." The HybridChunker addresses this by accounting for heading/caption tokens in its limit calculations.

---

## 6. Part Number / Alphanumeric Code Preservation

### The Problem

Alphanumeric identifiers (part numbers, model numbers, spec codes) are high-value tokens in technical catalogs. Standard tokenizers break them in non-obvious ways:
- `"AH-350-CW"` → `["AH", "-", "350", "-", "CW"]` — 5 tokens instead of 1
- `"12345-001"` → `["123", "45", "-", "001"]` — tokenizer dependent
- Fixed-size chunking may split `"Model AH-"` at a chunk boundary, with `"350"` in the next chunk

### Strategy 1: Regex-Protected Boundary Rules

Add part number patterns to your sentence splitter's "do not split here" rules. The key is to treat part numbers as atomic units during boundary detection:

```python
import re

# Pattern for common part number formats
PART_NUMBER_PATTERN = re.compile(
    r'\b[A-Z]{1,5}-?\d{3,6}(?:-[A-Z0-9]{1,5})?\b'  # e.g., AH-350, 12345-001
)

def safe_sentence_split(text: str) -> list[str]:
    """Split on sentence boundaries but not within part numbers."""
    # Temporarily replace part numbers with placeholders
    placeholders = {}
    masked = text
    for i, match in enumerate(PART_NUMBER_PATTERN.finditer(text)):
        placeholder = f"PARTNUM{i:04d}"
        placeholders[placeholder] = match.group()
        masked = masked.replace(match.group(), placeholder, 1)
    
    # Split masked text at sentence boundaries
    sentences = split_sentences(masked)
    
    # Restore part numbers
    return [
        restore_placeholders(s, placeholders) 
        for s in sentences
    ]
```

### Strategy 2: Extract to Metadata (Most Robust)

The most reliable approach: extract all part numbers and model numbers during chunking and store them in chunk metadata. This enables exact-match filtering even if the identifiers appear across chunk boundaries:

```python
PART_NUMBER_RE = re.compile(r'\b[A-Z]{1,5}-?\d{3,6}(?:-[A-Z0-9]{1,5})?\b')

def extract_identifiers(text: str) -> dict:
    """Extract technical identifiers for metadata storage."""
    return {
        "part_numbers": list(set(PART_NUMBER_RE.findall(text))),
        # Add other patterns as needed:
        # "model_numbers": ...,
        # "serial_patterns": ...,
    }

# At indexing time:
metadata["part_numbers"] = extract_identifiers(chunk_text)["part_numbers"]

# At retrieval time — exact match filter:
results = vector_store.similarity_search(
    query="installation requirements",
    filter={"part_numbers": {"$contains": "AH-350"}}
)
```

### Strategy 3: Overlap Sizing

For catalogs with dense part number tables, use larger overlap (15–20%) to ensure part numbers that appear near chunk boundaries are fully captured in both adjacent chunks. This is a simpler fallback when regex protection is impractical.

### Strategy 4: Hybrid BM25 + Vector Retrieval

Part numbers are exact-match candidates — they benefit heavily from sparse retrieval (BM25) alongside dense semantic retrieval. [Anthropic's contextual retrieval research](https://www.anthropic.com/news/contextual-retrieval) shows BM25 contribution at 40–45% of relevant hits for technical content with specific identifiers. Configure your pipeline with hybrid retrieval, weighting BM25 higher for queries that look like part number lookups (contain alphanumeric codes).

### Strategy 5: Tokenizer-Aware Boundary Protection

Use a tokenizer-aware splitter that never cuts mid-token. tiktoken's `RecursiveCharacterTextSplitter.from_tiktoken_encoder()` in LangChain respects token boundaries. Additionally, when using character-based splitting, never split on a hyphen if it's preceded and followed by alphanumeric characters (the `\w-\w` pattern typically indicates a part number or compound identifier).

---

## 7. Docling's Built-In Chunking

### Overview

Docling (originally IBM Research, now donated to LF AI & Data Foundation, 42,000+ GitHub stars) provides native structure-aware chunking that operates directly on its `DoclingDocument` format — preserving the parsed document hierarchy rather than operating on raw text.

### HierarchicalChunker

The base document-structure-driven chunker, available since Docling's initial release.

**How it works:**
- Splits the document based on structural hierarchy (headings, sections, list items, paragraphs) as detected by Docling's PDF parser
- Merges list items together by default (controllable via `merge_list_items`)
- Attaches all relevant metadata: headings, captions, page numbers, bounding boxes
- No token limit enforcement — chunks can be arbitrarily long
- `.text` field is kept separate from metadata enrichments

**Best for:** Document visualization, structure analysis, or when you want maximum fidelity to the document's logical organization without length constraints.

**Output metadata per chunk:**
```python
chunk.meta.headings    # List of heading strings above this chunk
chunk.meta.captions    # Table/figure captions associated with this chunk
chunk.meta.origin      # Source file reference
chunk.meta.doc_items   # The actual DoclingDocument items in this chunk
```

### HybridChunker (Recommended for RAG)

Introduced in **docling 2.9.0 / docling-core 2.8.0**, the HybridChunker applies tokenization-aware refinements on top of HierarchicalChunker output.

**How it works:**
1. Starts from HierarchicalChunker output
2. **Splits** oversized chunks to fit within `max_tokens` (accounting for metadata overhead)
3. **Merges** undersized consecutive chunks within the same section (same headings and captions)
4. Uses `semchunk` for plain-text splitting when hierarchical elements exceed limits
5. Exposes `get_text_for_embedding()` and `get_text_for_generation()` as separate methods

**Configuration:**
```python
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

EMBED_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = HuggingFaceTokenizer(
    tokenizer=AutoTokenizer.from_pretrained(EMBED_MODEL_ID),
    max_tokens=512,
)

chunker = HybridChunker(
    tokenizer=tokenizer,
    merge_peers=True,  # merge undersized adjacent chunks in same section (default: True)
)

# Convert and chunk
from docling.document_converter import DocumentConverter
doc = DocumentConverter().convert("catalog.pdf").document
chunks = list(chunker.chunk(dl_doc=doc))

# For embedding — enriched with heading context
for chunk in chunks:
    text_to_embed = chunker.contextualize(chunk=chunk)  
    # Returns: "Section Heading\n\nSubsection\n\nChunk text..."
    
    text_to_store = chunk.text  # Clean text without metadata enrichment
```

**Critical detail:** The `contextualize()` method returns heading/caption-enriched text for embedding, while `chunk.text` stores clean text. This separation is intentional — [as discussed in Docling's GitHub thread](https://github.com/docling-project/docling/discussions/191) — allowing downstream consumers to combine metadata and text as they see fit.

**OpenAI tokenizer variant:**
```python
# pip install 'docling-core[chunking-openai]'
import tiktoken
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

tokenizer = OpenAITokenizer(
    tokenizer=tiktoken.encoding_for_model("gpt-4o"),
    max_tokens=8192,
)
```

### Comparison: HierarchicalChunker vs HybridChunker

| Aspect | HierarchicalChunker | HybridChunker |
|--------|--------------------|-----------------------|
| Splitting | Hierarchy only, no length limits | Hierarchy + splits oversized (token-aware) |
| Merging | None | Merges undersized peers within same section |
| Token limits | Ignored | Enforced (includes metadata in calculation) |
| Metadata | headings, captions, origin | Same + contextualize() for embedding text |
| Use case | Structure visualization, debug | RAG / vector indexes |
| Introduced | Initial release | docling 2.9.0 |

Source: [Docling GitHub discussion #191](https://github.com/docling-project/docling/discussions/191) and [official chunking documentation](https://docling-project.github.io/docling/concepts/chunking/)

### Docling vs Custom Chunking for Technical Catalogs

| Factor | Docling HybridChunker | Custom Chunking |
|--------|----------------------|-----------------|
| Table preservation | ✅ Native (treats tables as atomic elements) | ⚠️ Requires explicit table detection logic |
| Header hierarchy | ✅ Automatic via DoclingDocument structure | ⚠️ Requires regex/HTML parsing |
| Token limit enforcement | ✅ Built-in, respects metadata overhead | Manual implementation |
| Part number protection | ❌ No native support | ✅ Fully customizable |
| Speed | 🟡 Slower (full PDF parse pipeline) | ✅ Can be lightweight |
| Framework integration | ✅ LlamaIndex, LangChain plugins | ✅ Universal |
| Markdown serialization for tables | ✅ Via custom serializers | Manual |

**Verdict for technical catalogs:** Start with Docling's `HybridChunker` for its superior table handling and heading hierarchy preservation. Layer custom regex logic on top for part number extraction and metadata enrichment.

### Integration with LlamaIndex

```python
from llama_index.node_parser.docling import DoclingNodeParser
from docling.chunking import HybridChunker

node_parser = DoclingNodeParser(
    chunker=HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
    )
)
```

Source: [OpenSearch + Docling RAG pipeline guide](https://opensearch.org/blog/building-powerful-rag-pipelines-with-docling-and-opensearch/)

---

## 8. Recommended End-to-End Pipeline for Technical PDF Catalogs

Based on all research above, here is the recommended pipeline for technical product catalogs:

```
PDF Input
    │
    ▼
[Docling DocumentConverter]
    │  ├── Table detection & structure preservation
    │  ├── Reading order determination  
    │  └── Heading hierarchy extraction
    │
    ▼
DoclingDocument (JSON)
    │
    ▼
[HybridChunker]
    │  ├── tokenizer = HuggingFaceTokenizer (aligned to embed model)
    │  ├── max_tokens = 512–1024 (based on embed model limit)
    │  └── merge_peers = True
    │
    ▼
Raw Chunks (text + meta.headings + meta.captions)
    │
    ▼
[Post-Processing]
    │  ├── Extract part numbers → store in metadata
    │  ├── Build breadcrumb path from headings
    │  ├── Add YAML front-matter metadata fields
    │  └── Optionally: Anthropic contextual enrichment (LLM-generated context)
    │
    ▼
[Text for Embedding] = breadcrumb + "\n\n" + chunker.contextualize(chunk)
[Metadata] = {source, doc_id, section_path, page, chunk_id, part_numbers, content_type, ...}
[Stored Text] = chunk.text (clean, for generation context)
    │
    ▼
Vector Database (with metadata filtering)
```

### Chunk Quality Checklist

- [ ] No chunk splits across a table row
- [ ] Table header row appears in every table chunk
- [ ] Section heading path prepended or available in metadata
- [ ] Token count verified (including metadata overhead) against embed model limit
- [ ] Part numbers extracted to metadata AND present in chunk text
- [ ] `content_type` field set (text / table / code / list)
- [ ] `page_number` recorded for PDF citation
- [ ] Overlap configured at 10–20% of chunk size

---

## 9. Key References

| Resource | URL | Coverage |
|----------|-----|----------|
| Anthropic Contextual Retrieval | https://www.anthropic.com/news/contextual-retrieval | Context preservation, +35-67% retrieval |
| NVIDIA Chunking Benchmark (2025) | https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/ | Page/token/section strategy comparison |
| Docling HybridChunker Docs | https://docling-project.github.io/docling/concepts/chunking/ | Official Docling chunking reference |
| Docling Advanced Chunking Discussion | https://github.com/docling-project/docling/discussions/191 | HybridChunker design rationale |
| Unstructured.io Best Practices | https://unstructured.io/blog/chunking-for-rag-best-practices | Table handling, smart chunking strategies |
| Structure-Aware Chunking Paper | https://www.ijournalse.org/index.php/ESJ/article/view/3380 | Academic: table chunking, RAGAS evaluation |
| Multimodal Document Chunking | https://arxiv.org/html/2506.16035v2 | Vision-guided table row chunking |
| arXiv Enterprise RAG | https://arxiv.org/pdf/2507.12425 | Table-aware + hybrid retrieval |
| Firecrawl 2026 Chunking Guide | https://www.firecrawl.dev/blog/best-chunking-strategies-rag | Strategy comparison with code examples |
| Databricks Ultimate Chunking Guide | https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089 | Comprehensive with code |
| ByteVagabond Enterprise RAG | https://bytevagabond.com/post/how-to-build-enterprise-ai-rag/ | Breadcrumb context pattern |
| Dell Tech Chunk Twice Retrieve Once | https://infohub.delltechnologies.com/es-es/p/chunk-twice-retrieve-once-rag-chunking-strategies-optimized-for-different-content-types/ | Content-type specific strategies |
| Sarthakai Layout-Aware Chunking | https://sarthakai.substack.com/p/improve-your-rag-accuracy-with-a | Table handling, layout principles |
| OpenSearch + Docling RAG Pipeline | https://opensearch.org/blog/building-powerful-rag-pipelines-with-docling-and-opensearch/ | Full integration example |
| MDPI Bioengineering Chunking Study | https://pmc.ncbi.nlm.nih.gov/articles/PMC12649634/ | Adaptive chunking 87% vs 13% fixed |
| Chroma Research: Evaluating Chunking | https://research.trychroma.com/evaluating-chunking | Precision/recall benchmarks by chunk size |
| Voyage AI Contextualized Embeddings | https://mongodb.com/company/blog/technical/contextualized-chunk-embeddings-combining-local-detail-with-global-context | Late chunking / contextualized embeddings |

---

*Report generated: February 27, 2026. Research covers publications and tooling through February 2026.*
