#!/usr/bin/env python3
"""Local web server for catalog2md. Run this on your own machine."""
import http.server
import json
import os
import sys
import tempfile
import base64
from pathlib import Path

# Add catalog2md to path
sys.path.insert(0, str(Path(__file__).parent))

PORT = 8080

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
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        action = data.get("action", "convert")

        if action == "convert":
            try:
                b64_data = data.get("pdf_base64", "")
                filename = data.get("filename", "upload.pdf")
                pdf_bytes = base64.b64decode(b64_data)

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name

                result = self.run_conversion(tmp_path, filename)
                os.unlink(tmp_path)

                self.send_json(result)
            except Exception as e:
                import traceback
                self.send_json({"error": str(e), "traceback": traceback.format_exc()}, 500)
        else:
            self.send_json({"error": f"Unknown action: {action}"}, 400)

    def run_conversion(self, pdf_path, filename):
        from catalog2md.extractors import ExtractionOrchestrator
        from catalog2md.chunker import chunk_page_results
        from catalog2md.validator import validate_conversion
        from catalog2md.writer import write_consolidated_markdown

        orchestrator = ExtractionOrchestrator(use_docling=True)
        page_results = orchestrator.extract(pdf_path)

        tmp_dir = Path(tempfile.mkdtemp())
        consolidated_path = tmp_dir / "output.md"
        consolidated_md = write_consolidated_markdown(
            page_results, consolidated_path, filename
        )

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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"  {args[0]}")


if __name__ == "__main__":
    print(f"\n  catalog2md web interface")
    print(f"  Open http://localhost:{PORT} in your browser\n")
    server = http.server.HTTPServer(("", PORT), CatalogHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
