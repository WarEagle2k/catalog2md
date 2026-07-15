#!/usr/bin/env python3
"""Local web server for catalog2md. Run this on your own machine."""
import argparse
import base64
import http.server
import json
import shutil
import sys
import tempfile
import threading
import uuid
from pathlib import Path

# Add catalog2md to path
sys.path.insert(0, str(Path(__file__).parent))

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # matches the 50MB limit advertised in the UI

# In-progress chunked uploads: upload_id -> {filename, total_chunks, chunks: {index: bytes}}
_uploads: dict[str, dict] = {}
_uploads_lock = threading.Lock()


class CatalogHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve from the 'web' subdirectory
        super().__init__(*args, directory=str(Path(__file__).parent / "web"), **kwargs)

    def do_POST(self):
        if self.path == "/api/convert":
            self.handle_convert()
        else:
            self.send_error(404)

    def handle_convert(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_UPLOAD_BYTES * 2:
                self.send_json({"error": "Request body too large."}, 413)
                return
            body = self.rfile.read(content_length)
            data = json.loads(body)
        except (ValueError, json.JSONDecodeError) as e:
            self.send_json({"error": f"Invalid request body: {e}"}, 400)
            return

        action = data.get("action", "convert")
        try:
            if action == "convert":
                self.handle_single_shot(data)
            elif action == "init":
                self.handle_init(data)
            elif action == "chunk":
                self.handle_chunk(data)
            elif action == "process":
                self.handle_process(data)
            else:
                self.send_json({"error": f"Unknown action: {action}"}, 400)
        except Exception as e:
            import traceback
            self.send_json({"error": str(e), "traceback": traceback.format_exc()}, 500)

    # -- single-shot upload -------------------------------------------------

    def handle_single_shot(self, data):
        pdf_bytes = base64.b64decode(data.get("pdf_base64", ""))
        filename = data.get("filename", "upload.pdf")
        self.convert_and_respond(pdf_bytes, filename)

    # -- chunked upload protocol (for PDFs too large for one request) -------

    def handle_init(self, data):
        total_chunks = int(data.get("total_chunks", 0))
        total_size = int(data.get("total_size", 0))
        if total_chunks < 1:
            self.send_json({"error": "total_chunks must be >= 1"}, 400)
            return
        if total_size > MAX_UPLOAD_BYTES:
            self.send_json({"error": "File exceeds 50MB limit."}, 413)
            return
        upload_id = uuid.uuid4().hex
        with _uploads_lock:
            _uploads[upload_id] = {
                "filename": data.get("filename", "upload.pdf"),
                "total_chunks": total_chunks,
                "chunks": {},
            }
        self.send_json({"upload_id": upload_id})

    def handle_chunk(self, data):
        upload_id = data.get("upload_id", "")
        chunk_index = int(data.get("chunk_index", -1))
        chunk_bytes = base64.b64decode(data.get("data", ""))
        with _uploads_lock:
            upload = _uploads.get(upload_id)
            if upload is None:
                self.send_json({"error": "Unknown or expired upload_id."}, 400)
                return
            if not 0 <= chunk_index < upload["total_chunks"]:
                self.send_json({"error": f"chunk_index {chunk_index} out of range."}, 400)
                return
            upload["chunks"][chunk_index] = chunk_bytes
            received = len(upload["chunks"])
        self.send_json({"received": received})

    def handle_process(self, data):
        upload_id = data.get("upload_id", "")
        with _uploads_lock:
            upload = _uploads.pop(upload_id, None)
        if upload is None:
            self.send_json({"error": "Unknown or expired upload_id."}, 400)
            return
        missing = [i for i in range(upload["total_chunks"]) if i not in upload["chunks"]]
        if missing:
            self.send_json({"error": f"Missing chunks: {missing[:10]}"}, 400)
            return
        pdf_bytes = b"".join(upload["chunks"][i] for i in range(upload["total_chunks"]))
        self.convert_and_respond(pdf_bytes, upload["filename"])

    # -- conversion ----------------------------------------------------------

    def convert_and_respond(self, pdf_bytes: bytes, filename: str):
        if len(pdf_bytes) > MAX_UPLOAD_BYTES:
            self.send_json({"error": "File exceeds 50MB limit."}, 413)
            return
        if not pdf_bytes.startswith(b"%PDF"):
            self.send_json({"error": "File does not look like a PDF."}, 400)
            return

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            result = self.run_conversion(tmp_path, filename)
            self.send_json(result)
        except Exception as e:
            import traceback
            self.send_json({"error": str(e), "traceback": traceback.format_exc()}, 500)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    def run_conversion(self, pdf_path, filename):
        from catalog2md.extractors import ExtractionOrchestrator
        from catalog2md.chunker import chunk_page_results
        from catalog2md.validator import validate_conversion
        from catalog2md.writer import write_consolidated_markdown

        orchestrator = ExtractionOrchestrator(use_docling=True)
        page_results = orchestrator.extract(pdf_path)

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            consolidated_path = tmp_dir / "output.md"
            consolidated_md = write_consolidated_markdown(
                page_results, consolidated_path, filename
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        chunks = chunk_page_results(
            page_results, source_filename=filename,
            min_tokens=512, max_tokens=1024,
        )

        report = validate_conversion(page_results, chunks, consolidated_md, filename)

        chunks_data = []
        for chunk in chunks:
            chunks_data.append({
                "chunk_num": chunk.chunk_num,
                "chunk_type": chunk.chunk_type.value,
                "section_heading": chunk.section_heading,
                "page_range": chunk.page_range,
                "token_count": chunk.token_count,
                "part_numbers": chunk.part_numbers,
                "content": chunk.content,
                "frontmatter": chunk.to_file_content(),
            })

        return {
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
            "chunks": chunks_data,
        }

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"  {args[0]}")


def main():
    parser = argparse.ArgumentParser(description="catalog2md web interface")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1; use 0.0.0.0 to expose on your LAN)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()

    print("\n  catalog2md web interface")
    print(f"  Open http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0', '') else args.host}:{args.port} in your browser\n")
    server = http.server.ThreadingHTTPServer((args.host, args.port), CatalogHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")


if __name__ == "__main__":
    main()
