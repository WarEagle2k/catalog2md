/* ===== catalog2md — Frontend Logic ===== */

const API_BASE = "/api";

// Upload config: base64 inflates by ~33%, so each chunk of original binary is
// kept small enough that the JSON body stays comfortably sized.
const CHUNK_RAW_SIZE = 500 * 1024; // 500KB of raw PDF per chunk
const SINGLE_UPLOAD_LIMIT = 600 * 1024; // PDFs under 600KB go single-shot
const MAX_FILE_SIZE = 50 * 1024 * 1024;

// State
let currentData = null;
let selectedFile = null;
let conversionSeconds = null;

// DOM refs
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileInfo = document.getElementById("file-info");
const fileName = document.getElementById("file-name");
const fileSize = document.getElementById("file-size");
const fileRemove = document.getElementById("file-remove");
const btnConvert = document.getElementById("btn-convert");
const processing = document.getElementById("processing");
const processingStatus = document.getElementById("processing-status");
const processingBarFill = document.getElementById("processing-bar-fill");
const errorBanner = document.getElementById("error-banner");
const errorMessage = document.getElementById("error-message");
const errorDismiss = document.getElementById("error-dismiss");
const resultsSection = document.getElementById("results-section");
const chunkSearch = document.getElementById("chunk-search");

// ===== FILE UPLOAD =====

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function setFile(file) {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
        showError("Please select a valid PDF file.");
        return;
    }
    if (file.size > MAX_FILE_SIZE) {
        showError("File exceeds 50MB limit.");
        return;
    }
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    dropZone.hidden = true;
    fileInfo.hidden = false;
    hideError();
}

function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    dropZone.hidden = false;
    fileInfo.hidden = true;
}

// Drop zone events
dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (files.length > 0) setFile(files[0]);
});

// Allow dropping a PDF anywhere on the page while the drop zone is visible
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (!dropZone.hidden && e.dataTransfer.files.length > 0) {
        setFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) setFile(fileInput.files[0]);
});

fileRemove.addEventListener("click", clearFile);

// ===== HELPERS =====

function arrayBufferToBase64(buffer) {
    // Convert in slices — per-byte string concatenation is quadratic on big files
    const bytes = new Uint8Array(buffer);
    const parts = [];
    const SLICE = 0x8000;
    for (let i = 0; i < bytes.length; i += SLICE) {
        parts.push(String.fromCharCode.apply(null, bytes.subarray(i, i + SLICE)));
    }
    return btoa(parts.join(""));
}

async function postJSON(url, data) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    });

    const responseText = await response.text();
    let result;
    try {
        result = JSON.parse(responseText);
    } catch (parseErr) {
        throw new Error(
            "Server returned invalid JSON (status " + response.status + "). " +
            "Response: " + responseText.substring(0, 500)
        );
    }

    if (!response.ok || result.error) {
        const detail = result.traceback
            ? result.error + "\n\n" + result.traceback.substring(0, 500)
            : result.error || "Server returned status " + response.status;
        throw new Error(detail);
    }

    return result;
}

function downloadBlob(text, filename) {
    const blob = new Blob([text], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
    }
}

const COPY_ICON = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="4" y="4" width="9" height="9" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M10 4V2a1 1 0 00-1-1H2a1 1 0 00-1 1v7a1 1 0 001 1h2" stroke="currentColor" stroke-width="1.2"/></svg>`;
const CHECK_ICON = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7l3 3 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="square"/></svg>`;

function flashCopied(btn, restoreHtml) {
    btn.classList.add("copied");
    btn.innerHTML = CHECK_ICON + " Copied";
    setTimeout(() => {
        btn.classList.remove("copied");
        btn.innerHTML = restoreHtml;
    }, 2000);
}

function catalogBaseName() {
    return currentData
        ? currentData.filename.replace(/\.pdf$/i, "")
        : "catalog";
}

// ===== PROCESSING =====

const statusMessages = [
    "Running extraction pipeline...",
    "Detecting tables and structured content...",
    "Extracting text and layout...",
    "Processing tables and part numbers...",
    "Chunking content...",
    "Validating conversion quality...",
    "Assembling Markdown output...",
    "Finalizing...",
];

function simulateProgress(abortSignal, startPct = 0) {
    let step = 0;
    let progress = startPct;
    const interval = setInterval(() => {
        if (abortSignal.aborted) {
            clearInterval(interval);
            return;
        }
        processingStatus.textContent = statusMessages[step];
        step = Math.min(step + 1, statusMessages.length - 1);

        // Asymptotic progress — never reaches 100 until done
        progress = Math.min(progress + (100 - progress) * 0.08, 92);
        processingBarFill.style.width = progress + "%";
    }, 3000);

    return () => clearInterval(interval);
}

function setProgress(message, pct) {
    processingStatus.textContent = message;
    processingBarFill.style.width = pct + "%";
}

async function uploadSingleShot(arrayBuffer, filename) {
    const b64 = arrayBufferToBase64(arrayBuffer);
    setProgress("Uploading PDF...", 10);
    return postJSON(`${API_BASE}/convert`, {
        action: "convert",
        pdf_base64: b64,
        filename: filename,
    });
}

async function uploadChunked(arrayBuffer, filename, onProcessingStart) {
    const totalSize = arrayBuffer.byteLength;
    const totalChunks = Math.ceil(totalSize / CHUNK_RAW_SIZE);

    // Step 1: Init upload session
    setProgress("Initializing upload...", 5);
    const initResult = await postJSON(`${API_BASE}/convert`, {
        action: "init",
        filename: filename,
        total_chunks: totalChunks,
        total_size: totalSize,
    });

    const uploadId = initResult.upload_id;

    // Step 2: Send chunks sequentially
    for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_RAW_SIZE;
        const end = Math.min(start + CHUNK_RAW_SIZE, totalSize);
        const chunkB64 = arrayBufferToBase64(arrayBuffer.slice(start, end));

        const uploadPct = 5 + ((i + 1) / totalChunks) * 30; // 5-35% for upload phase
        setProgress(`Uploading chunk ${i + 1} of ${totalChunks}...`, uploadPct);

        await postJSON(`${API_BASE}/convert`, {
            action: "chunk",
            upload_id: uploadId,
            chunk_index: i,
            data: chunkB64,
        });
    }

    // Step 3: Trigger processing (this call blocks until conversion completes)
    setProgress("Processing PDF...", 40);
    if (onProcessingStart) onProcessingStart();
    return postJSON(`${API_BASE}/convert`, {
        action: "process",
        upload_id: uploadId,
    });
}

async function startConversion() {
    if (!selectedFile) return;

    // UI: switch to processing state
    fileInfo.hidden = true;
    processing.hidden = false;
    hideError();
    resultsSection.hidden = true;
    currentData = null;
    processingBarFill.style.width = "0%";
    processingStatus.textContent = "Reading PDF file...";

    const abortController = new AbortController();
    let stopProgress = null;
    const startedAt = performance.now();

    try {
        const arrayBuffer = await selectedFile.arrayBuffer();
        const filename = selectedFile.name;

        let result;
        if (arrayBuffer.byteLength <= SINGLE_UPLOAD_LIMIT) {
            stopProgress = simulateProgress(abortController.signal, 10);
            result = await uploadSingleShot(arrayBuffer, filename);
        } else {
            // Large file: chunked upload, then simulated progress during processing
            result = await uploadChunked(arrayBuffer, filename, () => {
                stopProgress = simulateProgress(abortController.signal, 40);
            });
        }

        abortController.abort();
        if (stopProgress) stopProgress();

        conversionSeconds = (performance.now() - startedAt) / 1000;
        processingBarFill.style.width = "100%";
        processingStatus.textContent = "Conversion complete.";

        setTimeout(() => {
            processing.hidden = true;
            dropZone.hidden = true;
            fileInfo.hidden = false;
            currentData = result;
            renderResults(result);
        }, 600);

    } catch (err) {
        abortController.abort();
        if (stopProgress) stopProgress();
        processing.hidden = true;
        fileInfo.hidden = false;
        dropZone.hidden = true;
        showError(err.message);
    }
}

btnConvert.addEventListener("click", startConversion);

// ===== ERROR =====

function showError(msg) {
    errorMessage.textContent = msg;
    errorBanner.hidden = false;
}

function hideError() {
    errorBanner.hidden = true;
}

errorDismiss.addEventListener("click", hideError);
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !errorBanner.hidden) hideError();
});

// ===== TABS =====

const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".tab-panel");

tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((t) => t.classList.remove("active"));
        panels.forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById("panel-" + target).classList.add("active");
    });
});

// ===== RENDER RESULTS =====

function renderResults(data) {
    resultsSection.hidden = false;
    document.getElementById("results-filename").textContent = data.filename;

    const elapsedEl = document.getElementById("results-elapsed");
    if (conversionSeconds != null) {
        elapsedEl.textContent = conversionSeconds.toFixed(1) + "s";
        elapsedEl.hidden = false;
    } else {
        elapsedEl.hidden = true;
    }

    renderOverview(data.report);
    renderMarkdown(data.consolidated_md);
    renderChunks(data.chunks);

    // Reset chunk filters
    chunkSearch.value = "";
    document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    document.querySelector('.filter-btn[data-filter="all"]').classList.add("active");
    applyChunkFilters();

    // Switch to overview tab
    tabs.forEach((t) => t.classList.remove("active"));
    panels.forEach((p) => p.classList.remove("active"));
    tabs[0].classList.add("active");
    panels[0].classList.add("active");

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ===== OVERVIEW =====

function renderOverview(report) {
    // Validation
    const badge = document.getElementById("validation-badge");
    if (report.validation_passed) {
        badge.className = "validation-badge passed";
        badge.textContent = "PASSED";
    } else {
        badge.className = "validation-badge failed";
        badge.textContent = "FAILED";
    }

    // Stats
    document.getElementById("stat-pages").textContent = report.pages_processed;
    document.getElementById("stat-pages-sub").textContent =
        "of " + report.total_pages + " total";
    document.getElementById("stat-chunks").textContent = report.chunk_count;

    // Chunk type breakdown
    const chunkBreakdown = report.chunk_type_breakdown || {};
    const chunkParts = Object.entries(chunkBreakdown)
        .map(([k, v]) => v + " " + k)
        .join(", ");
    document.getElementById("stat-chunks-sub").textContent = chunkParts || "";

    document.getElementById("stat-tables").textContent = report.total_tables;
    document.getElementById("stat-parts").textContent = report.total_part_numbers;

    // Extraction breakdown
    const breakdown = report.extraction_breakdown || {};
    const barsEl = document.getElementById("breakdown-bars");
    barsEl.innerHTML = "";

    const maxVal = Math.max(...Object.values(breakdown), 1);

    const methodColors = {
        docling: "method-docling",
        pdfplumber: "method-pdfplumber",
        claude_vision: "method-claude",
        skipped: "method-fallback",
    };

    for (const [method, count] of Object.entries(breakdown)) {
        const pct = (count / maxVal) * 100;
        const row = document.createElement("div");
        row.className = "breakdown-row";
        row.innerHTML = `
            <span class="breakdown-label">${escapeHtml(method)}</span>
            <div class="breakdown-bar-track">
                <div class="breakdown-bar-fill ${methodColors[method] || ""}" style="width: ${pct}%"></div>
            </div>
            <span class="breakdown-value">${count} pg</span>
        `;
        barsEl.appendChild(row);
    }

    // Issues
    const issuesSection = document.getElementById("issues-section");
    const issuesList = document.getElementById("issues-list");
    issuesList.innerHTML = "";

    if (report.flagged_issues && report.flagged_issues.length > 0) {
        issuesSection.hidden = false;
        report.flagged_issues.forEach((issue) => {
            const li = document.createElement("li");
            li.textContent = issue;
            issuesList.appendChild(li);
        });
    } else {
        issuesSection.hidden = true;
    }
}

// ===== MARKDOWN =====

function renderMarkdown(md) {
    document.getElementById("md-content").textContent = md;
}

document.getElementById("btn-copy-md").addEventListener("click", async function () {
    if (!currentData) return;
    const orig = this.innerHTML;
    await copyText(currentData.consolidated_md);
    flashCopied(this, orig);
});

document.getElementById("btn-download-md").addEventListener("click", () => {
    if (!currentData) return;
    downloadBlob(currentData.consolidated_md, catalogBaseName() + ".md");
});

// ===== CHUNKS =====

const chunksList = document.getElementById("chunks-list");

function renderChunks(chunks) {
    chunksList.innerHTML = "";

    chunks.forEach((chunk, idx) => {
        const card = document.createElement("div");
        card.className = "chunk-card";
        card.dataset.type = chunk.chunk_type;
        card.dataset.index = idx;

        const typeBadgeClass = {
            table: "type-table",
            mixed: "type-mixed",
        }[chunk.chunk_type] || "type-text";

        const pageRange = chunk.page_range || "—";
        const tokens = chunk.token_count || 0;

        card.innerHTML = `
            <div class="chunk-card-header">
                <span class="chunk-num">#${chunk.chunk_num}</span>
                <span class="chunk-type-badge ${typeBadgeClass}">${escapeHtml(chunk.chunk_type)}</span>
                <span class="chunk-heading">${escapeHtml(chunk.section_heading || "Untitled")}</span>
                <div class="chunk-meta">
                    <span class="chunk-meta-item">pp. <span>${escapeHtml(String(pageRange))}</span></span>
                    <span class="chunk-meta-item"><span>${tokens}</span> tok</span>
                </div>
                <span class="chunk-expand-icon">▶</span>
            </div>
            <div class="chunk-body">
                ${chunk.part_numbers && chunk.part_numbers.length > 0
                    ? `<div class="chunk-parts">${chunk.part_numbers.map(p => `<span class="chunk-part-tag">${escapeHtml(p)}</span>`).join("")}</div>`
                    : ""
                }
                <div class="chunk-body-content">${escapeHtml(chunk.content)}</div>
                <div class="chunk-body-actions">
                    <button class="btn-secondary btn-copy-chunk" data-index="${idx}">
                        ${COPY_ICON}
                        Copy
                    </button>
                    <button class="btn-secondary btn-download-chunk" data-index="${idx}">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1v9M3 7l4 4 4-4" stroke="currentColor" stroke-width="1.2" stroke-linecap="square"/><path d="M1 12h12" stroke="currentColor" stroke-width="1.2" stroke-linecap="square"/></svg>
                        Download .md
                    </button>
                </div>
            </div>
        `;

        chunksList.appendChild(card);
    });
}

// Delegated once — NOT inside renderChunks, so repeated conversions don't
// stack duplicate listeners (which caused double downloads/copies before).
chunksList.addEventListener("click", async (e) => {
    const header = e.target.closest(".chunk-card-header");
    if (header) {
        header.parentElement.classList.toggle("expanded");
        return;
    }

    const copyBtn = e.target.closest(".btn-copy-chunk");
    if (copyBtn && currentData) {
        const chunk = currentData.chunks[parseInt(copyBtn.dataset.index)];
        await copyText(chunk.frontmatter || chunk.content);
        flashCopied(copyBtn, COPY_ICON + " Copy");
        return;
    }

    const dlBtn = e.target.closest(".btn-download-chunk");
    if (dlBtn && currentData) {
        const chunk = currentData.chunks[parseInt(dlBtn.dataset.index)];
        const text = chunk.frontmatter || chunk.content;
        const num = String(chunk.chunk_num).padStart(3, "0");
        downloadBlob(text, `${catalogBaseName()}_chunk_${num}.md`);
    }
});

// ===== CHUNK FILTERING & SEARCH =====

function applyChunkFilters() {
    if (!currentData) return;
    const activeBtn = document.querySelector(".filter-btn.active");
    const filter = activeBtn ? activeBtn.dataset.filter : "all";
    const query = chunkSearch.value.trim().toLowerCase();

    let visible = 0;
    document.querySelectorAll(".chunk-card").forEach((card) => {
        const chunk = currentData.chunks[parseInt(card.dataset.index)];
        const typeMatch = filter === "all" || card.dataset.type === filter;
        let searchMatch = true;
        if (query) {
            const haystack = (
                (chunk.section_heading || "") + "\n" +
                chunk.content + "\n" +
                (chunk.part_numbers || []).join(" ")
            ).toLowerCase();
            searchMatch = haystack.includes(query);
        }
        const show = typeMatch && searchMatch;
        card.dataset.hidden = show ? "false" : "true";
        if (show) visible++;
    });

    const total = currentData.chunks.length;
    const countEl = document.getElementById("chunks-count");
    countEl.textContent = (visible === total)
        ? total + " chunks"
        : visible + " of " + total + " chunks";
}

document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        applyChunkFilters();
    });
});

chunkSearch.addEventListener("input", applyChunkFilters);

// Expand / collapse all (only affects currently visible chunks)
document.getElementById("btn-expand-all").addEventListener("click", () => {
    document.querySelectorAll('.chunk-card:not([data-hidden="true"])')
        .forEach((c) => c.classList.add("expanded"));
});

document.getElementById("btn-collapse-all").addEventListener("click", () => {
    document.querySelectorAll(".chunk-card")
        .forEach((c) => c.classList.remove("expanded"));
});

// Download all chunks as a single Markdown file (frontmatter included)
document.getElementById("btn-download-chunks").addEventListener("click", () => {
    if (!currentData) return;
    const combined = currentData.chunks
        .map((c) => c.frontmatter || c.content)
        .join("\n\n");
    downloadBlob(combined, catalogBaseName() + "_chunks.md");
});

// ===== UTILITIES =====

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
