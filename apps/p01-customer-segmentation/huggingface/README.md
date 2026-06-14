---
title: Customer Segmentation Lab
emoji: 📊
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 5.23.0
app_file: app.py
pinned: false
license: mit
---

# Customer Grouping Lab (HF Space)

Browser lab for **Willamette Valley Bank**-style customer segmentation. Upload a CSV or use bundled sample data, pick K, run K-Means, view segment stats.

For full React UI + inference summary, see the portfolio repo. This Space runs the **core ML pipeline** only.

## Secrets (optional)

| Secret | Purpose |
|--------|---------|
| `INFERENCE_URL` | Portfolio `/api/inference/summarize` URL for stakeholder summary |

## Local test

```bash
pip install -r requirements.txt
gradio app.py
```
