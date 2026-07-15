"""FastAPI web server for catalog2md.

Modern replacement for the old stdlib http.server backend:
- multipart/form-data uploads (no base64-JSON chunking protocol)
- real-time conversion progress streamed to the browser via Server-Sent Events
- conversions run in worker threads behind a small in-memory job store
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # matches the 50MB limit advertised in the UI
JOB_TTL_SECONDS = 60 * 60  # finished jobs are kept for an hour

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="catalog2md", docs_url=None, redoc_url=None)


class Job:
    """One conversion run: an event log the SSE endpoint tails, plus the result."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.created = time.time()
        self.events: list[dict] = []
        self.result: dict | None = None
        self.error: dict | None = None
        self.done = False
        self.lock = threading.Lock()

    def emit(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)

    def finish(self, *, result: dict | None = None, error: dict | None = None) -> None:
        with self.lock:
            self.result = result
            self.error = error
            self.done = True
            if error is not None:
                self.events.append({"type": "error", **error})
            else:
                self.events.append({"type": "done"})


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        for job_id in [j.id for j in _jobs.values() if j.done and j.created < cutoff]:
            del _jobs[job_id]


def _get_job(job_id: str) -> Job:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id")
    return job


# ---------------------------------------------------------------------------
# Conversion worker
# ---------------------------------------------------------------------------

def _run_job(job: Job, pdf_bytes: bytes, filename: str) -> None:
    tmp_path = None

    def progress(message: str, pct: float | None = None) -> None:
        event: dict = {"type": "progress", "message": message}
        if pct is not None:
            event["pct"] = round(min(pct, 99.0), 1)
        job.emit(event)

    try:
        from .chunker import chunk_page_results
        from .extractors import ExtractionOrchestrator
        from .validator import validate_conversion
        from .writer import render_consolidated_markdown

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        progress("Initializing extraction pipeline...", 22)
        orchestrator = ExtractionOrchestrator(use_docling=True)

        def status_cb(msg: str, current: int | None = None, total: int | None = None):
            # Extraction spans 25% -> 85% of the bar; page counts give real progress
            pct = 25 + (current / total) * 60 if current and total else None
            progress(msg, pct)

        progress("Extracting pages...", 25)
        page_results = orchestrator.extract(tmp_path, status_callback=status_cb)

        progress("Chunking content...", 87)
        chunks = chunk_page_results(
            page_results, source_filename=filename,
            min_tokens=512, max_tokens=1024,
        )

        progress("Assembling Markdown output...", 92)
        consolidated_md = render_consolidated_markdown(
            page_results, filename, total_chunk_count=len(chunks)
        )

        progress("Validating conversion quality...", 96)
        report = validate_conversion(page_results, chunks, consolidated_md, filename)

        job.finish(result={
            "filename": filename,
            "report": {
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
            },
            "consolidated_md": consolidated_md,
            "chunks": [
                {
                    "chunk_num": c.chunk_num,
                    "chunk_type": c.chunk_type.value,
                    "section_heading": c.section_heading,
                    "page_range": c.page_range,
                    "token_count": c.token_count,
                    "part_numbers": c.part_numbers,
                    "content": c.content,
                    "frontmatter": c.to_file_content(),
                }
                for c in chunks
            ],
        })
    except Exception as e:
        job.finish(error={"error": str(e), "traceback": traceback.format_exc()})
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/convert")
async def convert(file: UploadFile = File(...)):
    _prune_jobs()

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50MB limit.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="File does not look like a PDF.")

    job = Job()
    with _jobs_lock:
        _jobs[job.id] = job

    filename = file.filename or "upload.pdf"
    threading.Thread(
        target=_run_job, args=(job, pdf_bytes, filename), daemon=True
    ).start()
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = _get_job(job_id)

    async def stream():
        sent = 0
        while True:
            with job.lock:
                pending = job.events[sent:]
                finished = job.done and sent + len(pending) >= len(job.events)
            for event in pending:
                yield f"data: {json.dumps(event)}\n\n"
            sent += len(pending)
            if finished:
                return
            await asyncio.sleep(0.2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str):
    job = _get_job(job_id)
    if not job.done:
        raise HTTPException(status_code=409, detail="Job still running.")
    if job.error is not None:
        return JSONResponse(job.error, status_code=500)
    return job.result


# Static frontend — mounted last so /api routes take precedence
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
