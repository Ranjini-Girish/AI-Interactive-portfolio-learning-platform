import { useCallback, useEffect, useState } from 'react';
import {
  getCategories,
  getHealth,
  getProducts,
  getRecommendations,
  logClick,
  type Product,
} from './api';

const USER_ID = 'user-0042';

export default function App() {
  const [health, setHealth] = useState<{ ok: boolean; products: number } | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState<string>('');
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [reco, setReco] = useState<Product[]>([]);
  const [alpha, setAlpha] = useState(0.6);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [loadingReco, setLoadingReco] = useState(true);

  const loadReco = useCallback(async () => {
    setLoadingReco(true);
    try {
      const items = await getRecommendations(USER_ID, alpha);
      setReco(items);
    } finally {
      setLoadingReco(false);
    }
  }, [alpha]);

  useEffect(() => {
    getHealth().then(setHealth);
    getCategories().then(setCategories);
    loadReco();
  }, [loadReco]);

  useEffect(() => {
    setLoadingCatalog(true);
    getProducts(category || undefined)
      .then(setCatalog)
      .finally(() => setLoadingCatalog(false));
  }, [category]);

  async function handleProductClick(p: Product) {
    await logClick(USER_ID, p.product_id);
    await loadReco();
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <header style={{ marginBottom: '1.5rem' }}>
        <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>Columbia Sportswear · Portfolio P03</p>
        <h1 style={{ margin: '0.25rem 0' }}>Hybrid Recommendation Shop</h1>
        <p style={{ color: 'var(--muted)' }}>
          Collaborative filtering + content similarity · user <code>{USER_ID}</code>
        </p>
        {health && (
          <p style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
            API ok · {health.products} products seeded
          </p>
        )}
      </header>

      <section style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <strong>For you</strong>
          <label style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
            CF weight α={alpha.toFixed(1)}
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={alpha}
              onChange={(e) => setAlpha(Number(e.target.value))}
              style={{ display: 'block', width: 160 }}
            />
          </label>
          <button type="button" className="ghost" onClick={loadReco}>
            Refresh
          </button>
        </div>
        {loadingReco ? (
          <div className="grid">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton" />
            ))}
          </div>
        ) : (
          <ProductGrid items={reco} onClick={handleProductClick} highlight />
        )}
      </section>

      <section>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <strong>Browse</strong>
          <button type="button" className={category ? 'ghost' : ''} onClick={() => setCategory('')}>
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              className={category === c ? '' : 'ghost'}
              onClick={() => setCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>
        {loadingCatalog ? (
          <div className="grid">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="skeleton" />
            ))}
          </div>
        ) : (
          <ProductGrid items={catalog.slice(0, 12)} onClick={handleProductClick} />
        )}
      </section>
    </div>
  );
}

function ProductGrid({
  items,
  onClick,
  highlight,
}: {
  items: Product[];
  onClick: (p: Product) => void;
  highlight?: boolean;
}) {
  return (
    <div className="grid">
      {items.map((p) => (
        <button
          key={p.product_id}
          type="button"
          className="card"
          style={{
            textAlign: 'left',
            padding: 0,
            cursor: 'pointer',
            border: highlight ? '1px solid var(--retail)' : undefined,
          }}
          onClick={() => onClick(p)}
        >
          <img src={p.image_url} alt="" style={{ width: '100%', aspectRatio: '1', objectFit: 'cover' }} />
          <div style={{ padding: '0.65rem' }}>
            <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{p.title}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>${p.price.toFixed(2)}</div>
          </div>
        </button>
      ))}
    </div>
  );
}
