from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = {"ok": True}
        elif self.path.startswith("/api/tables/"):
            body = {"data": []}
        else:
            body = {"data": []}
        b = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print("[mock-db-api] listening on 127.0.0.1:8001")
    HTTPServer(("127.0.0.1", 8001), H).serve_forever()
