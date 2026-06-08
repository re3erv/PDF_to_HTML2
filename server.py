"""Локальный HTTP-сервер для просмотра проекта с готовыми Brotli-файлами."""

from argparse import ArgumentParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class BrotliStaticHandler(SimpleHTTPRequestHandler):
    """Отдаёт *.json.br как JSON, предварительно сжатый Brotli."""

    def guess_type(self, path):
        if path.endswith(".json.br"):
            return "application/json; charset=utf-8"
        return super().guess_type(path)

    def end_headers(self):
        if self.path.split("?", 1)[0].endswith(".json.br"):
            self.send_header("Content-Encoding", "br")
            self.send_header("Vary", "Accept-Encoding")
        super().end_headers()


def main():
    parser = ArgumentParser(description="Запустить локальный сервер PDF_to_HTML")
    parser.add_argument("--bind", default="127.0.0.1", help="адрес сервера")
    parser.add_argument("--port", type=int, default=8000, help="порт сервера")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.bind, args.port), BrotliStaticHandler)
    print(f"Откройте http://{args.bind}:{args.port}/index.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
