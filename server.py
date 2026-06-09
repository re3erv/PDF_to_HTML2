"""Serve the generated viewer and mark precompressed Brotli JSON correctly."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os


class BrotliRequestHandler(SimpleHTTPRequestHandler):
    def guess_type(self, path: str) -> str:
        if path.endswith(".json.br"):
            return "application/json"
        return super().guess_type(path)

    def end_headers(self) -> None:
        if self.path.split("?", 1)[0].endswith(".json.br"):
            self.send_header("Content-Encoding", "br")
            self.send_header("Vary", "Accept-Encoding")
        super().end_headers()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Viewer: http://127.0.0.1:{port}/index_word_select_v24.html")
    ThreadingHTTPServer(("127.0.0.1", port), BrotliRequestHandler).serve_forever()
