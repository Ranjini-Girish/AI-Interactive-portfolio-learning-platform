# P03 — Hybrid Recommendation Engine

Retail product discovery with **collaborative filtering + content-based** hybrid ranking (Columbia Sportswear portfolio project).

## Stack

| Layer | Tech |
|-------|------|
| API | Flask, scikit-learn, SQLite (500 products, 10k events) |
| Frontend | React, Vite |

> Mentor checklist mentions MongoDB + Postgres — this scaffold uses **SQLite** for zero-Docker local runs. Optional `docker-compose.yml` is included for a future dual-store migration.

## Quick start

```powershell
cd apps/p03-recommendations/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
python app.py

# new terminal
cd apps/p03-recommendations/frontend
npm install
npm run dev
```

- Shop UI: **http://localhost:5175**
- API: **http://localhost:8002/health**
- Recommend: `GET /recommend/user-0042?alpha=0.6&limit=20`

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Status + counts |
| GET | `/categories` | Product categories |
| GET | `/products?category=` | Catalog browse |
| GET | `/recommend/<user_id>` | Hybrid ranked list (`alpha` = CF weight) |
| POST | `/interactions` | Log view/click/cart/purchase |

## Mentor checklist

| Step | Verify |
|------|--------|
| **s1** | 500 products + 10k interactions (`python seed.py`) |
| **s2** | Cold user gets popularity fallback; α slider changes results |
| **s3** | Click product → refresh updates "For you" row; skeleton loaders |

## Ports (with P01/P02)

| App | Backend | Frontend |
|-----|---------|----------|
| P01 | 8000 | 5173 |
| P02 | 8001 | 5174 |
| P03 | **8002** | **5175** |
| Website | — | 3200 |

## Optional Docker (Postgres + Mongo)

```powershell
docker compose up -d
```

Use this when migrating from SQLite to the dual-store schema in the mentor step.
