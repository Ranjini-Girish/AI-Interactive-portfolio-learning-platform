# Apps workspace

Build each portfolio project here. The **main website** is `../portfolio-mentor-platform/` — run it on **http://localhost:3200** for portfolio, demos, and Build Lab.

**P01 is scaffolded and runnable.** See `p01-customer-segmentation/README.md`.

```powershell
# Terminal 1 — backend
cd apps/p01-customer-segmentation/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd apps/p01-customer-segmentation/frontend
npm install
npm run dev
```

Upload `data/customers.csv` at http://localhost:5173 — then mark mentor steps in http://localhost:3200.

---

**P02 is scaffolded.** See `p02-churn-api/README.md`.

```powershell
# Train + API (port 8001)
cd apps/p02-churn-api/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python train.py
uvicorn main:app --reload --port 8001

# Dashboard (port 5174)
cd apps/p02-churn-api/frontend
npm install
npm run dev
```

Open http://localhost:5174 → score a customer or **Run batch (100)** → filter/export audit log.

---

**P03 is scaffolded.** See `p03-recommendations/README.md`.

```powershell
cd apps/p03-recommendations/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
python app.py

cd apps/p03-recommendations/frontend
npm install
npm run dev
```

Shop at http://localhost:5175 — adjust α slider for CF vs content blend.
