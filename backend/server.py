#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地下商业街导航系统 —— 后端服务（仅依赖 Python 标准库）。

接口：
  GET /            前端演示页面
  GET /api/map     地图数据（节点、通道、扶梯、电梯、店铺营业状态）
  GET /api/pois    可选起终点（按类型分组，店铺含营业状态）
  GET /api/route?start=M1&end=P1&mode=fastest[&now=12:00]   路径规划

运行：python3 backend/server.py [端口]   默认 8000
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mall_data import CORRIDORS, ESCALATORS, ELEVATORS
from pathfinder import Mall, is_open, MODES

MALL = Mall()
FRONTEND_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "frontend", "index.html")


def _now_param(query):
    vals = query.get("now")
    return vals[0] if vals else None


class Handler(BaseHTTPRequestHandler):
    server_version = "UndergroundMallNav/1.0"

    # ---------- 响应工具 ----------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- 路由 ----------
    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                self._send_html(FRONTEND_PAGE)
            elif url.path == "/api/map":
                self._handle_map(query)
            elif url.path == "/api/pois":
                self._send_json(MALL.list_pois(now=_now_param(query)))
            elif url.path == "/api/route":
                self._handle_route(query)
            else:
                self._send_json({"error": "接口不存在"}, 404)
        except ValueError as e:   # 未营业终点 / 节点不存在 / 无可达路径 / 参数非法
            self._send_json({"error": str(e)}, 400)
        except Exception as e:    # noqa: BLE001
            self._send_json({"error": f"服务器内部错误: {e}"}, 500)

    def _handle_map(self, query):
        now = _now_param(query)
        nodes = {}
        for nid, n in MALL.nodes.items():
            item = dict(n)
            if n["type"] == "shop":
                item["open"] = is_open(n, now)
            nodes[nid] = item
        self._send_json({"nodes": nodes, "corridors": CORRIDORS,
                         "escalators": ESCALATORS, "elevators": ELEVATORS})

    def _handle_route(self, query):
        start = query.get("start", [""])[0]
        end = query.get("end", [""])[0]
        mode = query.get("mode", ["fastest"])[0]
        if not start or not end:
            self._send_json({"error": "缺少参数 start 或 end"}, 400)
            return
        if mode not in MODES:
            self._send_json({"error": f"未知的规划模式: {mode}"}, 400)
            return
        self._send_json(MALL.find_route(start, end, mode=mode, now=_now_param(query)))

    def log_message(self, fmt, *args):
        sys.stderr.write("[server] " + fmt % args + "\n")


def main(port=8000):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"地下商业街导航系统已启动: http://localhost:{port}")
    print("按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
