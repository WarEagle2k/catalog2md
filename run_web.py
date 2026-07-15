#!/usr/bin/env python3
"""Launch the catalog2md web interface (FastAPI + uvicorn). Run on your own machine."""
import argparse
import sys
from pathlib import Path

# Add catalog2md to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(description="catalog2md web interface")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (default: 127.0.0.1; use 0.0.0.0 to expose on your LAN)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()

    try:
        import uvicorn
        from catalog2md.server import app
    except ImportError as e:
        print(f"\n  Missing web server dependency: {e.name or e}")
        print("  Install with: pip install fastapi uvicorn python-multipart\n")
        sys.exit(1)

    display_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "") else args.host
    print("\n  catalog2md web interface")
    print(f"  Open http://{display_host}:{args.port} in your browser\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
