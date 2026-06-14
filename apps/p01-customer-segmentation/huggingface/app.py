"""Gradio Space — Customer Segmentation Lab (deploy to Hugging Face Spaces)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import gradio as gr
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from segmentation import run_kmeans  # noqa: E402
from validation import parse_csv, profile_dataframe  # noqa: E402

SAMPLE = BACKEND / "data" / "customers.csv"
_state: dict = {"df": None}


def load_sample() -> tuple[str, str]:
    raw = SAMPLE.read_bytes()
    df = parse_csv(raw)
    _state["df"] = df
    prof = profile_dataframe(df)
    return f"Loaded {prof['row_count']} sample customers.", _stats_text(prof)


def load_upload(file) -> tuple[str, str]:
    if file is None:
        return "Upload a CSV first.", ""
    raw = Path(file.name).read_bytes()
    try:
        df = parse_csv(raw)
    except ValueError as exc:
        return f"CSV error: {exc}", ""
    _state["df"] = df
    prof = profile_dataframe(df)
    return f"Loaded {prof['row_count']} customers.", _stats_text(prof)


def _stats_text(prof: dict) -> str:
    lines = [f"Rows: {prof['row_count']}", f"Columns: {', '.join(prof['columns'])}"]
    for col, s in prof.get("stats", {}).items():
        lines.append(f"{col}: min={s['min']:.0f} mean={s['mean']:.0f} max={s['max']:.0f}")
    return "\n".join(lines)


def run_segment(k: int) -> tuple[str, pd.DataFrame, str]:
    df = _state.get("df")
    if df is None:
        return "Load data first.", pd.DataFrame(), ""

    result = run_kmeans(df, int(k))
    rows = []
    for c in result["centroids"]:
        rows.append(
            {
                "Segment": c["segment_name"],
                "Avg spend": round(c["monthly_spend"], 2),
                "Avg balance": round(c["avg_balance"], 2),
                "Avg txns": round(c["txn_count"], 2),
            }
        )
    table = pd.DataFrame(rows)
    metrics = (
        f"k={result['metrics']['k']} · "
        f"silhouette={result['metrics']['silhouette_score']:.3f} · "
        f"inertia={result['metrics']['inertia']:.0f}"
    )

    summary = ""
    infer_url = os.environ.get("INFERENCE_URL", "").rstrip("/")
    if infer_url:
        try:
            r = requests.post(
                f"{infer_url}/summarize",
                json={
                    "segments": {
                        "centroids": result["centroids"],
                        "metrics": result["metrics"],
                    },
                    "company": "Willamette Valley Bank",
                },
                timeout=60,
            )
            if r.ok:
                summary = r.json().get("summary", "")
        except Exception as exc:  # noqa: BLE001
            summary = f"(Inference unavailable: {exc})"

    return metrics, table, summary or "Add INFERENCE_URL secret to enable AI stakeholder summary."


with gr.Blocks(title="Customer Segmentation Lab") as demo:
    gr.Markdown(
        "# Customer Grouping Lab\n"
        "Upload bank customer CSV or use sample data → choose K → run K-Means clustering."
    )
    with gr.Row():
        sample_btn = gr.Button("Load practice data", variant="primary")
        upload = gr.File(label="Or upload CSV", file_types=[".csv"])
    status = gr.Textbox(label="Status", interactive=False)
    stats = gr.Textbox(label="Dataset stats", interactive=False, lines=4)
    k = gr.Slider(2, 8, value=4, step=1, label="Number of groups (K)")
    run_btn = gr.Button("Create customer groups")
    metrics = gr.Textbox(label="Model metrics", interactive=False)
    table = gr.Dataframe(label="Segment centroids")
    summary = gr.Textbox(label="Stakeholder summary (via inference API)", lines=5)

    sample_btn.click(load_sample, outputs=[status, stats])
    upload.change(load_upload, inputs=upload, outputs=[status, stats])
    run_btn.click(run_segment, inputs=k, outputs=[metrics, table, summary])

if __name__ == "__main__":
    demo.launch()
