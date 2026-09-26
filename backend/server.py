"""零依赖 HTTP 服务: 提供导航 REST API 与前端演示页面。

接口:
    GET  /api/map              完整图数据(节点/边/楼层)
    GET  /api/places?type=     可选地点列表(entrance/shop/service/parking)
    POST /api/route            {"start": id, "goal": id,
                                "preference": none|escalator|elevator}
    GET  /                     前端演示页面
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .graph import build_default_mall
from .router import RouteError, plan_route

# frontend/ 与 backend/ 同级
FRONTEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "frontend"))

GRAPH = build_default_mall()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "MallNav/1.0"

    # ---------- 工具 ----------
    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, rel_path: str) -> None:
        # 防目录穿越
        full = os.path.normpath(os.path.join(FRONTEND_DIR, rel_path))
        if not full.startswith(FRONTEND_DIR) or not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type",
                         CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args) -> None:  # 简洁日志
        print("[http] %s" % (fmt % args))

    # ---------- 路由 ----------
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)

        if path == "/api/map":
            self._send_json(GRAPH.to_dict())
            return
        if path == "/api/places":
            node_type = qs.get("type", [None])[0]
            places = GRAPH.places(node_type)
            self._send_json({"places": [n.to_dict() for n in places]})
            return
        if path in ("/", "/index.html"):
            self._send_static("index.html")
            return
        # 其他静态资源
        if path.startswith("/"):
            self._send_static(path.lstrip("/"))
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/route":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._send_json({"error": {"code": "BAD_JSON",
                                       "message": "请求体不是合法 JSON"}}, 400)
            return

        start = payload.get("start", "")
        goal = payload.get("goal", "")
        preference = payload.get("preference", "none")
        if preference not in ("none", "escalator", "elevator"):
            preference = "none"
        try:
            result = plan_route(GRAPH, start, goal, preference)
        except RouteError as exc:
            self._send_json({"error": {"code": exc.code,
                                       "message": exc.message}}, 400)
        else:
            self._send_json({"route": result})


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    httpd = create_server("0.0.0.0", port)
    print(f"地下商业街导航系统已启动: http://127.0.0.1:{port}")
    print("按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
