const LOCAL_DIM = 64;

/** Deterministic dev fallback when HF_TOKEN is unset — not for production RAG quality. */
export function embedLocally(texts: string[]): number[][] {
  return texts.map((text) => {
    const vec = new Array<number>(LOCAL_DIM).fill(0);
    const tokens = text.toLowerCase().split(/\W+/).filter(Boolean);
    for (const tok of tokens) {
      let h = 0;
      for (let i = 0; i < tok.length; i++) {
        h = (h * 31 + tok.charCodeAt(i)) >>> 0;
      }
      vec[h % LOCAL_DIM] += 1;
    }
    const norm = Math.sqrt(vec.reduce((s, v) => s + v * v, 0)) || 1;
    return vec.map((v) => v / norm);
  });
}

export function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}
