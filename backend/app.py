"""Flask 应用: 提供地图数据 API、路径规划 API, 并托管前端演示页面。"""
from __future__ import annotations
import os

from flask import Flask, jsonify, request, send_from_directory

from .data import FLOORS, SELECTABLE_TYPES, TYPE_LABELS, build_graph
from .router import RouteError, find_route, parse_now

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    g = build_graph()

    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    @app.get("/api/map")
    def api_map():
        now_minutes = parse_now(request.args.get("now"))
        nodes = []
        for n in g.nodes.values():
            item = {
                "id": n.id, "name": n.name, "floor": n.floor,
                "type": n.type, "x": n.x, "y": n.y,
                "type_label": TYPE_LABELS.get(n.type, n.type),
                "selectable": n.type in SELECTABLE_TYPES,
            }
            if n.type == "shop":
                item["open"] = g.is_shop_open(n.id, now_minutes)
                item["hours"] = n.hours
            else:
                item["open"] = True
            nodes.append(item)
        return jsonify({
            "floors": FLOORS,
            "nodes": nodes,
            "edges": [
                {"a": e.a, "b": e.b, "kind": e.kind,
                 "meters": e.meters, "floors": e.floors}
                for e in g.edges
            ],
        })

    @app.post("/api/route")
    def api_route():
        data = request.get_json(silent=True) or {}
        try:
            now_minutes = parse_now(data.get("now"))
            result = find_route(g, data.get("start"), data.get("end"),
                                now_minutes)
        except RouteError as ex:
            return jsonify({"error": str(ex), "code": ex.code}), 400
        return jsonify(result)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "资源不存在", "code": "not_found"}), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
