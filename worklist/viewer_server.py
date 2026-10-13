from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from summary_api import Handler, ROOT


class ViewerHandler(Handler):
    def do_GET(self):
        if urlsplit(self.path).path == "/":
            data = (ROOT / "viewer.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8082), ViewerHandler)
    print("Viewer and API: http://localhost:8082", flush=True)
    print("Keep this terminal open. Ctrl+C stops the viewer and API.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
