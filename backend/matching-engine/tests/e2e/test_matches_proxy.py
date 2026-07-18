import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import config


class _EchoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"echoed_path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence stdlib access logs
        pass


@pytest.fixture
def upstream_server():
    server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()


@pytest.mark.asyncio
async def test_matches_proxy_forwards_query_string_and_body(client, db_conn, upstream_server):
    port = upstream_server.server_address[1]
    original_url = config.MATCHING_API_URL
    config.MATCHING_API_URL = f"http://127.0.0.1:{port}"
    try:
        resp = await client.get("/matches?sector=fintech&limit=5")
    finally:
        config.MATCHING_API_URL = original_url

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"echoed_path": "/matches?sector=fintech&limit=5"}
