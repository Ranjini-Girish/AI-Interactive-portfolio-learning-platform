# Deploy P01 to Hugging Face Spaces

## Option A — Gradio Space (recommended)

1. Create a new Space at [huggingface.co/new-space](https://huggingface.co/new-space) → **Gradio**.
2. Upload the contents of `apps/p01-customer-segmentation/huggingface/` **plus** copy `backend/` into the Space:
   ```
   huggingface/
     app.py
     README.md
     requirements.txt
     backend/          ← copy from ../backend (segmentation.py, validation.py, data/)
   ```
3. **Settings → Secrets** (optional):
   - `INFERENCE_URL` = `https://YOUR-VERCEL-APP.vercel.app/api/inference`
4. Space builds automatically. Copy the Space URL to Vercel:
   ```
   NEXT_PUBLIC_DEMO_P01_URL=https://huggingface.co/spaces/YOUR_USER/customer-segmentation-lab
   ```

## Option B — Full React app

Deploy FastAPI backend to Render/Railway and static Vite build to Vercel/Cloudflare. Set:

```
VITE_API_URL=https://your-api.onrender.com
VITE_INFERENCE_URL=https://YOUR-VERCEL-APP.vercel.app/api/inference
VITE_LAB_API_URL=https://YOUR-VERCEL-APP.vercel.app/api/lab
```

## Local Gradio test

```powershell
cd apps/p01-customer-segmentation/huggingface
pip install -r requirements.txt
# Ensure backend/ is sibling or copied next to app.py
python app.py
```
