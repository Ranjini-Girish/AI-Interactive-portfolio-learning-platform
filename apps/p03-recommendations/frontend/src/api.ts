const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8002';

export type Product = {
  product_id: string;
  title: string;
  category: string;
  tags: string[];
  image_url: string;
  price: number;
  cf_score?: number;
  content_score?: number;
  popularity?: number;
};

export async function getHealth() {
  const r = await fetch(`${API}/health`);
  return r.json();
}

export async function getCategories(): Promise<string[]> {
  const r = await fetch(`${API}/categories`);
  const d = await r.json();
  return d.categories;
}

export async function getProducts(category?: string): Promise<Product[]> {
  const q = category ? `?category=${encodeURIComponent(category)}` : '';
  const r = await fetch(`${API}/products${q}`);
  const d = await r.json();
  return d.items;
}

export async function getRecommendations(
  userId: string,
  alpha: number,
): Promise<Product[]> {
  const r = await fetch(
    `${API}/recommend/${encodeURIComponent(userId)}?limit=20&alpha=${alpha}`,
  );
  const d = await r.json();
  return d.items;
}

export async function logClick(userId: string, productId: string) {
  await fetch(`${API}/interactions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, product_id: productId, event_type: 'click' }),
  });
}
