# AI Career Transition & Real-World Experience Simulator



Interactive platform for **non-IT beginners**, **career returners**, **freshers**, and **upskilling professionals** — simulating real company work with an AI mentor.



## Tech stack



| Layer | Technology |

|-------|------------|

| Frontend | Next.js 15, React 19, Tailwind CSS 4, ShadCN-style UI |

| Backend | Node.js, Express 5, TypeScript |

| Database | PostgreSQL 16 (Docker local / Fly.io Postgres) |

| AI | OpenAI API (optional — local fallbacks available) |

| Auth | JWT |



## Monorepo structure



```

career-simulator/

├── apps/

│   ├── web/                 # Next.js → Vercel

│   └── api/                 # Express → Fly.io (Docker)

├── packages/shared/

├── Dockerfile.api           # Production API image
├── fly.toml                 # Fly.io app config
├── FLY-DEPLOY.md            # Fly.io deploy guide
├── docker-compose.yml       # Local Postgres :5433

└── PHASE-1.md … PHASE-10.md

```



## Quick start (local)



```powershell

cd career-simulator

npm install

copy .env.example .env

npm run db:up

npm run dev

```



- **Web:** http://localhost:3000  

- **API:** http://localhost:4000/api/health  



## All phases — complete



| Phase | Feature |

|-------|---------|

| 1 | Project setup |

| 2 | JWT authentication |

| 3 | Resume analyzer |

| 4 | Job matching |

| 5 | AI mentor (SSE) |

| 6 | Job simulations |

| 7 | Progress dashboard |

| 8 | Portfolio generator |

| 9 | Mock interviews |

| 10 | **Deployment** |



See **PHASE-1.md** through **PHASE-10.md** for walkthroughs.



## Production deployment



### API — Fly.io (Docker)

1. Install Fly CLI: https://fly.io/docs/flyctl/install/
2. Follow **`FLY-DEPLOY.md`** (Postgres + `fly deploy`)
3. API URL: `https://career-simulator-api.fly.dev`

```powershell
cd career-simulator
fly auth login
fly deploy
```

### Web — Vercel

1. Import repo → **Root Directory:** `career-simulator/apps/web`
2. Env: `NEXT_PUBLIC_API_URL=https://career-simulator-api.fly.dev`
3. Deploy

Full checklist: **FLY-DEPLOY.md**



## Scripts



| Command | Description |

|---------|-------------|

| `npm run dev` | API + web locally |

| `npm run build` | Build all workspaces |

| `npm run build:api` | API only |

| `npm run start:api` | Run built API |

| `npm run docker:api` | Build production Docker image |

| `npm run db:up` | Start local Postgres |


