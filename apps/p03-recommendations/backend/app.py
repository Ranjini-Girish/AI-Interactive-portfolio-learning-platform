from __future__ import annotations

from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_cors import CORS

from db import count_interactions, count_products, init_db
from ranker import hybrid_recommend, load_catalog
from seed import seed

app = Flask(__name__)
CORS(
    app,
    origins=[
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
)


@app.before_request
def ensure_seeded() -> None:
    init_db()
    if count_products() == 0:
        seed()


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "products": count_products(),
            "interactions": count_interactions(),
        }
    )


@app.get("/products")
def products():
    category = request.args.get("category")
    df = load_catalog()
    if category:
        df = df[df["category"] == category]
    items = df.head(100).to_dict(orient="records")
    for item in items:
        item["tags"] = item["tags"].split(",")
    return jsonify({"items": items, "count": len(items)})


@app.get("/categories")
def categories():
    df = load_catalog()
    cats = sorted(df["category"].unique().tolist())
    return jsonify({"categories": cats})


@app.get("/recommend/<user_id>")
def recommend(user_id: str):
    limit = min(int(request.args.get("limit", 20)), 50)
    alpha = float(request.args.get("alpha", 0.6))
    items = hybrid_recommend(user_id, alpha=alpha, limit=limit)
    return jsonify({"user_id": user_id, "alpha": alpha, "items": items})


@app.post("/interactions")
def log_interaction():
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    product_id = data.get("product_id")
    event_type = data.get("event_type", "click")
    if not user_id or not product_id:
        return jsonify({"error": "user_id and product_id required"}), 422
    if event_type not in ("view", "click", "cart", "purchase"):
        return jsonify({"error": "invalid event_type"}), 422

    from db import connect

    with connect() as conn:
        conn.execute(
            "INSERT INTO interactions (user_id, product_id, event_type, ts) VALUES (?,?,?,?)",
            (user_id, product_id, event_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=True)
