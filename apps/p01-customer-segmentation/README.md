# P01 — Customer Grouping Lab (beginner-friendly)

Interactive lab for **non-IT learners** — group bank customers by spending habits, no coding required.

**Resume anchor:** Customer segmentation with Scikit-learn (Willamette Valley Bank).

## Stack

| Layer | Tech | Version |
|-------|------|---------|
| Frontend | React, Vite, Recharts | React 19 |
| Backend | FastAPI, pandas, scikit-learn | FastAPI 0.115, sklearn 1.6 |

## Quick start (8 commands)

```powershell
# 1 — backend venv
cd apps/p01-customer-segmentation/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2 — run API
uvicorn main:app --reload --port 8000

# 3 — new terminal, frontend
cd apps/p01-customer-segmentation/frontend
npm install
npm run dev
```

Open **http://localhost:5173** and upload `data/customers.csv`.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | `{ "ok": true }` |
| POST | `/upload` | CSV file → row count + column stats |
| POST | `/segment` | Body `{ "k": 4 }` → labels, centroids, silhouette |

## Verify mentor checklist

1. Frontend on **:5173**, backend `/health` returns `{ "ok": true }`
2. Upload sample CSV → see 80 rows + stats table
3. Upload bad CSV (missing column) → readable error
4. Run K-means with k=4 → scatter plot + segment tables
5. Change k slider → re-run segmentation
6. Export JSON downloads segment payload

## Project structure

```
p01-customer-segmentation/
├── backend/
│   ├── main.py
│   ├── validation.py
│   ├── segmentation.py
│   └── requirements.txt
├── frontend/
│   └── src/App.tsx
└── data/customers.csv
```

## Your next tasks (mentor platform)

Mark steps **s1–s4** complete in [Resume Mentor Lab](http://localhost:3200/projects/customer-segmentation-lab) after you verify each checklist item.

**Step s5 (you):** Add screenshot here, deploy demo, link from portfolio platform case study page.
