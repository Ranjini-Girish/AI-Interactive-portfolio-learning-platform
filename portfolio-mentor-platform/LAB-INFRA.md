# Lab infrastructure setup

## 1. Hugging Face (summaries + RAG embeddings)

### Get your token (follow in order)

1. **Sign up / log in** at [huggingface.co](https://huggingface.co) and **confirm your email** (tokens stay disabled until verified).
2. Open **[Access Tokens](https://huggingface.co/settings/tokens)** (profile → Settings → Access Tokens).
3. Click **New token** → choose **Fine-grained**.
4. Name it e.g. `portfolio-lab-local`.
5. Enable permission: **Make calls to Inference Providers** (required for BART summarization + MiniLM embeddings).
6. Click **Create token** and copy the `hf_…` value immediately (shown once).

Direct link: [Create fine-grained token](https://huggingface.co/settings/tokens/new?tokenType=fineGrained)

### Add keys locally

**Option A — interactive script (Windows):**

```powershell
cd portfolio-mentor-platform
.\scripts\setup-lab-env.ps1
# or double-click SETUP-LAB-ENV.bat
```

**Option B — manual `.env.local`:**

```
HF_TOKEN=hf_...
HF_SUMMARY_MODEL=facebook/bart-large-cnn
HF_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Restart `npm run dev`, then open **`/lab/setup`** and click **Re-check connection**.

### Vercel (production)

Project → Settings → Environment Variables — add the same three `HF_*` keys. Redeploy after saving.

**API routes**

| Route | Purpose |
|-------|---------|
| `POST /api/inference/summarize` | Stakeholder summary from segment centroids |
| `POST /api/inference/embed` | `{ texts: string[] }` → embeddings |
| `POST /api/inference/rag/search` | `{ query, documents, top_k }` → ranked chunks |

**UI:** `/lab/rag` — Policy Document RAG demo (Lab 3)

---

## 2. Supabase (shareable proof links)

1. Create a free project at [supabase.com](https://supabase.com).
2. SQL Editor → paste and run `supabase/schema.sql`.
3. Settings → API → copy **Project URL** and **service_role** key (server only, never expose in browser).
4. Add env vars:
   ```
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
   NEXT_PUBLIC_APP_URL=https://your-vercel-app.vercel.app
   ```

**API:** `POST /api/lab/runs` → `{ id, proof_url }`  
**Public page:** `/lab/proof/[uuid]`

P01 Step 4: **Save & get shareable proof link** after summarizing segments.

---

## 3. Hugging Face Spaces (host P01 demo)

See `apps/p01-customer-segmentation/DEPLOY-HF-SPACE.md`.

After deploy, set:
```
NEXT_PUBLIC_DEMO_P01_URL=https://huggingface.co/spaces/YOU/customer-segmentation-lab
```

Optional Space secret:
```
INFERENCE_URL=https://your-vercel-app.vercel.app/api/inference
```

---

## Local dev (all features)

```powershell
# Terminal 1 — portfolio (3200)
cd portfolio-mentor-platform
npm run dev

# Terminal 2 — P01 (8000 + 5173)
cd portfolio-mentor-platform
.\START-PORTFOLIO.bat
```

P01 proxies `/inference-api` and `/lab-api` to port 3200 automatically.
