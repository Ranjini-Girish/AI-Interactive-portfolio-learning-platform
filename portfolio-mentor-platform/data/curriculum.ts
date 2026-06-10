export type Step = {
  id: string;
  title: string;
  instruction: string;
  hint?: string;
  verifyChecklist: string[];
};

export type Milestone = {
  id: string;
  title: string;
  outcome: string;
  steps: Step[];
};

export type Project = {
  slug: string;
  order: number;
  phase: 1 | 2 | 3 | 4;
  phaseLabel: string;
  title: string;
  company: string;
  domain: 'banking' | 'retail' | 'insurance' | 'genai';
  stack: string[];
  resumeAnchor: string;
  elevatorPitch: string;
  portfolioHighlight: string;
  estimatedHours: number;
  repoFolder: string;
  milestones: Milestone[];
};

export type LearnerProfile = {
  name: string;
  title: string;
  email: string;
  phone: string;
  summary: string[];
  skills: Record<string, string[]>;
};

export const learner: LearnerProfile = {
  name: 'Ranjini Gowda',
  title: 'Gen AI Engineer | AI/ML Engineer',
  email: 'Racgowda18@gmail.com',
  phone: '619-736-0266',
  summary: [
    '8+ years in Python, AI/ML, and GenAI across banking, insurance, and retail.',
    'Production LLM apps with Claude, OpenAI, LangChain, LangGraph, and AWS SageMaker.',
    'RAG, multi-agent orchestration, LLM evals, and secure code-review systems.',
  ],
  skills: {
    'AI/ML & GenAI': [
      'PyTorch',
      'RAG',
      'LLM Agents',
      'RLHF',
      'SFT',
      'Prompt Engineering',
    ],
    Backend: ['Python', 'FastAPI', 'Flask', 'Django', 'Spring Boot', 'REST'],
    Data: ['Pandas', 'NumPy', 'ETL', 'PostgreSQL', 'MongoDB', 'Redis'],
    MLOps: ['MLflow', 'CI/CD', 'Docker', 'Kubernetes', 'AWS'],
  },
};

export const phases = [
  {
    id: 1,
    label: 'Foundation ML & APIs',
    weeks: '1–3',
    focus: 'Segmentation, churn, FastAPI services — Willamette Valley Bank patterns',
  },
  {
    id: 2,
    label: 'Retail Intelligence',
    weeks: '4–6',
    focus: 'Recommendations, forecasting, caching — Columbia Sportswear patterns',
  },
  {
    id: 3,
    label: 'Insurance AI Systems',
    weeks: '7–9',
    focus: 'Fraud ML, RAG, event pipelines — Pacific Specialty patterns',
  },
  {
    id: 4,
    label: 'Enterprise GenAI',
    weeks: '10–14',
    focus: 'Code review, multi-agent PR flow, LLM evals — Credit One patterns',
  },
] as const;

export const projects: Project[] = [
  {
    slug: 'customer-segmentation-lab',
    order: 1,
    phase: 1,
    phaseLabel: 'Foundation ML & APIs',
    title: 'Customer Segmentation Lab',
    company: 'Willamette Valley Bank',
    domain: 'banking',
    stack: ['Python', 'scikit-learn', 'Pandas', 'React', 'Recharts'],
    resumeAnchor:
      'Built customer segmentation models using Scikit-learn clustering algorithms to analyze transaction behavior.',
    elevatorPitch:
      'Interactive dashboard that clusters bank customers from transaction CSVs and explains each segment.',
    portfolioHighlight: 'End-to-end EDA → clustering → visual storytelling for stakeholders.',
    estimatedHours: 12,
    repoFolder: 'apps/p01-customer-segmentation',
    milestones: [
      {
        id: 'm1',
        title: 'Data pipeline',
        outcome: 'Clean transaction dataset loaded and profiled in the UI.',
        steps: [
          {
            id: 's1',
            title: 'Scaffold React + FastAPI monorepo',
            instruction:
              'Open the Customer Grouping Lab demo. Confirm the app loads and shows the three-step wizard (Load data → Group customers → Explore results).',
            hint: 'Launch from Portfolio → Customer Segmentation Lab, or open http://localhost:5173 after running START-PORTFOLIO.bat.',
            verifyChecklist: [
              'App opens at localhost:5173 without errors',
              'Welcome screen or Step 1 is visible',
              'No red “data service offline” banner (backend on port 8000)',
            ],
          },
          {
            id: 's2',
            title: 'Upload & validate CSV',
            instruction:
              'In Step 1, click **Start with practice data (recommended)**. Confirm customer count and summary stats appear.',
            verifyChecklist: [
              'Practice data loads with one click',
              'Summary shows row count and spending stats',
              'Step 1 shows a green “complete” message',
            ],
          },
        ],
      },
      {
        id: 'm2',
        title: 'Clustering engine',
        outcome: 'K-means (or DBSCAN) assigns segment labels with silhouette score.',
        steps: [
          {
            id: 's3',
            title: 'Feature engineering endpoint',
            instruction:
              'In Step 2, choose how many groups (try 4), then click **Create customer groups**. Confirm results appear in Step 3.',
            verifyChecklist: [
              'Grouping completes without errors',
              'Quality score is shown after grouping',
              'Changing group count and re-running works',
            ],
          },
          {
            id: 's4',
            title: 'Segment explorer UI',
            instruction:
              'Explore Step 3: scatter chart colored by group, and the top spenders table per segment.',
            verifyChecklist: [
              'Chart shows customers as colored dots',
              'Each group has a plain-English name',
              'Top spenders table lists customers per group',
            ],
          },
        ],
      },
      {
        id: 'm3',
        title: 'Portfolio polish',
        outcome: 'Deployable demo with README and architecture diagram.',
        steps: [
          {
            id: 's5',
            title: 'Write case study page',
            instruction:
              'Add a `/case-study` route in the portfolio platform linking to this app. Document business problem, approach, and metrics screenshot.',
            verifyChecklist: [
              'README has setup steps under 10 commands',
              'Screenshot of dashboard in README',
              'Lists sklearn + FastAPI versions used',
            ],
          },
        ],
      },
    ],
  },
  {
    slug: 'churn-prediction-api',
    order: 2,
    phase: 1,
    phaseLabel: 'Foundation ML & APIs',
    title: 'Churn Prediction API',
    company: 'Willamette Valley Bank',
    domain: 'banking',
    stack: ['FastAPI', 'scikit-learn', 'PostgreSQL', 'React'],
    resumeAnchor:
      'Contributed to predictive modeling projects for customer churn and engagement analysis.',
    elevatorPitch:
      'REST API serving churn scores with model versioning and a banker-facing risk table.',
    portfolioHighlight: 'Production-style API design with OpenAPI docs and batch scoring.',
    estimatedHours: 14,
    repoFolder: 'apps/p02-churn-api',
    milestones: [
      {
        id: 'm1',
        title: 'Model + API core',
        outcome: 'Train/test split, logistic regression or gradient boosting, `/predict` endpoint.',
        steps: [
          {
            id: 's1',
            title: 'Train baseline model',
            instruction:
              'Script `train.py` saves `model.joblib` + `metadata.json` (AUC, feature list, trained_at). Use synthetic or public telco churn dataset.',
            verifyChecklist: ['AUC logged > 0.75 on holdout', 'Model artifact gitignored but reproducible via train script'],
          },
          {
            id: 's2',
            title: 'FastAPI predict route',
            instruction:
              'Implement `POST /predict` (single) and `POST /predict/batch`. Return probability, risk band (low/medium/high), and top 3 SHAP-style feature drivers (can be coefficients).',
            verifyChecklist: ['OpenAPI `/docs` loads', 'Batch endpoint handles 100 rows', 'Invalid payload returns 422 with details'],
          },
        ],
      },
      {
        id: 'm2',
        title: 'Ops-ready layer',
        outcome: 'Postgres logging, health checks, React ops dashboard.',
        steps: [
          {
            id: 's3',
            title: 'Prediction audit log',
            instruction:
              'Store each prediction in SQLite or Postgres: timestamp, customer_id, score, model_version.',
            verifyChecklist: ['GET /predictions returns paginated history', 'Health check verifies DB connectivity'],
          },
          {
            id: 's4',
            title: 'Banker dashboard',
            instruction:
              'React table: sort by churn score, filter by risk band, CSV export.',
            verifyChecklist: ['Live fetch from API', 'Loading and error states', 'Mobile-responsive layout'],
          },
        ],
      },
    ],
  },
  {
    slug: 'hybrid-recommendation-engine',
    order: 3,
    phase: 2,
    phaseLabel: 'Retail Intelligence',
    title: 'Hybrid Recommendation Engine',
    company: 'Columbia Sportswear',
    domain: 'retail',
    stack: ['Python', 'Flask', 'React', 'PostgreSQL', 'MongoDB'],
    resumeAnchor:
      'Designed scalable recommendation systems using hybrid approaches (collaborative filtering + content-based filtering).',
    elevatorPitch:
      'Product discovery app blending user-item CF with catalog content features.',
    portfolioHighlight: 'Classic two-tower retail ML with A/B-ready ranking endpoint.',
    estimatedHours: 18,
    repoFolder: 'apps/p03-recommendations',
    milestones: [
      {
        id: 'm1',
        title: 'Catalog + interactions',
        outcome: 'MongoDB catalog, Postgres interactions, seed scripts.',
        steps: [
          {
            id: 's1',
            title: 'Dual-store schema',
            instruction:
              'MongoDB: products (title, category, tags, image_url). Postgres: user_id, product_id, event_type, timestamp.',
            verifyChecklist: ['Seed 500 products and 10k events', 'Docker compose for both DBs'],
          },
        ],
      },
      {
        id: 'm2',
        title: 'Hybrid ranker',
        outcome: 'CF + content similarity merged with configurable weights.',
        steps: [
          {
            id: 's2',
            title: 'Implement ranker service',
            instruction:
              'Flask `GET /recommend/{user_id}?limit=20`. Merge CF scores (implicit ALS or item-item) with content cosine similarity. Query param `alpha` weights CF vs content.',
            verifyChecklist: ['Cold-start user gets popular + content fallback', 'Response time < 200ms on seed data'],
          },
          {
            id: 's3',
            title: 'Shop UI',
            instruction:
              'React grid: hero product, personalized row, category filters. Click logs interaction back to API.',
            verifyChecklist: ['Click updates recommendations on refresh', 'Skeleton loaders during fetch'],
          },
        ],
      },
    ],
  },
  {
    slug: 'demand-forecast-dashboard',
    order: 4,
    phase: 2,
    phaseLabel: 'Retail Intelligence',
    title: 'Demand Forecast Dashboard',
    company: 'Columbia Sportswear',
    domain: 'retail',
    stack: ['Python', 'scikit-learn', 'React', 'Chart.js'],
    resumeAnchor:
      'Built demand forecasting models using regression techniques to optimize inventory planning.',
    elevatorPitch:
      'SKU-level weekly forecast with seasonality and promo flags for inventory planners.',
    portfolioHighlight: 'Time-series feature engineering visible in the UI.',
    estimatedHours: 14,
    repoFolder: 'apps/p04-demand-forecast',
    milestones: [
      {
        id: 'm1',
        title: 'Forecast pipeline',
        outcome: 'Rolling-window regression with MAPE displayed per SKU.',
        steps: [
          {
            id: 's1',
            title: 'Time-series features',
            instruction:
              'Backend builds lag features (1,4,8 weeks), rolling means, holiday flags. Train per-SKU or global model with SKU embeddings.',
            verifyChecklist: ['MAPE computed on last 8 weeks holdout', 'Forecast horizon selectable 4–12 weeks'],
          },
          {
            id: 's2',
            title: 'Planner dashboard',
            instruction:
              'Line chart actual vs predicted, inventory risk badges (stockout/overstock).',
            verifyChecklist: ['SKU dropdown', 'Export forecast CSV', 'Tooltips explain features used'],
          },
        ],
      },
    ],
  },
  {
    slug: 'cached-reco-api',
    order: 5,
    phase: 2,
    phaseLabel: 'Retail Intelligence',
    title: 'Cached Recommendation API',
    company: 'Columbia Sportswear',
    domain: 'retail',
    stack: ['Flask', 'Redis', 'Docker'],
    resumeAnchor:
      'Built RESTful APIs using Flask to serve personalized recommendations; caching strategies reduced API latency during peak traffic.',
    elevatorPitch:
      'Extend P03 with Redis cache layer, cache stampede protection, and latency metrics.',
    portfolioHighlight: 'Demonstrates performance engineering on top of ML serving.',
    estimatedHours: 10,
    repoFolder: 'apps/p05-cached-reco-api',
    milestones: [
      {
        id: 'm1',
        title: 'Redis cache layer',
        outcome: 'Sub-50ms p95 on cache hits; metrics endpoint.',
        steps: [
          {
            id: 's1',
            title: 'Add Redis with TTL strategy',
            instruction:
              'Cache key `reco:{user_id}:{alpha}`. TTL 5 min. Track hit/miss counters exposed at `/metrics`.',
            verifyChecklist: ['Second identical request is faster', 'Metrics show hit rate', 'Graceful degradation if Redis down'],
          },
        ],
      },
    ],
  },
  {
    slug: 'claims-fraud-scorer',
    order: 6,
    phase: 3,
    phaseLabel: 'Insurance AI Systems',
    title: 'Claims Fraud Risk Scorer',
    company: 'Pacific Specialty Insurance',
    domain: 'insurance',
    stack: ['Python', 'XGBoost', 'FastAPI', 'React'],
    resumeAnchor:
      'Built predictive models for insurance claims risk analysis, fraud detection, and policy optimization.',
    elevatorPitch:
      'Claims triage UI with fraud score, reason codes, and adjuster queue.',
    portfolioHighlight: 'Tabular ML with explainability for regulated domain.',
    estimatedHours: 16,
    repoFolder: 'apps/p06-fraud-scorer',
    milestones: [
      {
        id: 'm1',
        title: 'Fraud model + queue',
        outcome: 'Scored queue with SLA sorting for adjusters.',
        steps: [
          {
            id: 's1',
            title: 'Train fraud classifier',
            instruction:
              'Use synthetic claims dataset. Features: amount, provider history, time deltas, geo mismatch flags.',
            verifyChecklist: ['Precision@top10% reported', 'Reason codes mapped to top features'],
          },
          {
            id: 's2',
            title: 'Adjuster workbench',
            instruction:
              'React queue: filter high-risk, mark reviewed, add notes persisted via API.',
            verifyChecklist: ['Audit trail per claim', 'Role badge UI (demo only)'],
          },
        ],
      },
    ],
  },
  {
    slug: 'policy-document-rag',
    order: 7,
    phase: 3,
    phaseLabel: 'Insurance AI Systems',
    title: 'Policy Document RAG',
    company: 'Pacific Specialty Insurance',
    domain: 'insurance',
    stack: ['Python', 'FAISS', 'OpenAI or local embeddings', 'FastAPI', 'React'],
    resumeAnchor:
      'Developed RAG-based systems using FAISS and vector search for semantic retrieval of policy documents.',
    elevatorPitch:
      'Ask questions against policy PDFs with cited snippets and confidence.',
    portfolioHighlight: 'Full RAG stack: ingest, chunk, embed, retrieve, generate.',
    estimatedHours: 20,
    repoFolder: 'apps/p07-policy-rag',
    milestones: [
      {
        id: 'm1',
        title: 'Ingestion + index',
        outcome: 'PDFs chunked, embedded, stored in FAISS with metadata.',
        steps: [
          {
            id: 's1',
            title: 'Document pipeline',
            instruction:
              'Upload PDFs, extract text, chunk 512 tokens with overlap, embed, build FAISS index saved to disk.',
            verifyChecklist: ['Reindex endpoint', 'Chunk count shown in admin panel'],
          },
        ],
      },
      {
        id: 'm2',
        title: 'Grounded Q&A',
        outcome: 'Chat UI returns answer + source citations.',
        steps: [
          {
            id: 's2',
            title: 'RAG query endpoint',
            instruction:
              'POST /ask with question. Retrieve top-k, compose prompt, return answer + `[doc, page, snippet]` citations.',
            verifyChecklist: ['Refuses when no relevant chunks', 'Citations clickable in UI', 'Latency logged'],
          },
        ],
      },
    ],
  },
  {
    slug: 'claims-summarizer',
    order: 8,
    phase: 3,
    phaseLabel: 'Insurance AI Systems',
    title: 'Claims Summarization Copilot',
    company: 'Pacific Specialty Insurance',
    domain: 'insurance',
    stack: ['Python', 'LLM API', 'FastAPI', 'React'],
    resumeAnchor:
      'Implemented LLM-based automation for document processing, claims summarization, and customer query handling.',
    elevatorPitch:
      'Upload claim notes + photos metadata; get structured summary, next actions, and customer reply draft.',
    portfolioHighlight: 'Structured LLM output with JSON schema validation.',
    estimatedHours: 14,
    repoFolder: 'apps/p08-claims-summarizer',
    milestones: [
      {
        id: 'm1',
        title: 'Structured summarization',
        outcome: 'JSON summary schema enforced server-side.',
        steps: [
          {
            id: 's1',
            title: 'Schema-validated LLM output',
            instruction:
              'Define schema: incident_summary, injuries, coverage_flags, recommended_actions[]. Validate with pydantic; retry on failure.',
            verifyChecklist: ['Invalid LLM JSON triggers retry', 'UI renders all schema fields'],
          },
        ],
      },
    ],
  },
  {
    slug: 'insurance-event-pipeline',
    order: 9,
    phase: 3,
    phaseLabel: 'Insurance AI Systems',
    title: 'Real-Time Claims Event Pipeline',
    company: 'Pacific Specialty Insurance',
    domain: 'insurance',
    stack: ['Python', 'Redis', 'FastAPI', 'WebSockets', 'React'],
    resumeAnchor:
      'Built real-time data processing pipelines using Redis caching and event-driven architecture.',
    elevatorPitch:
      'Live event stream: claim filed → scored → routed; dashboard shows throughput and lag.',
    portfolioHighlight: 'Event-driven architecture with live UI subscription.',
    estimatedHours: 16,
    repoFolder: 'apps/p09-event-pipeline',
    milestones: [
      {
        id: 'm1',
        title: 'Event bus + live dashboard',
        outcome: 'Redis pub/sub or streams powering WebSocket feed.',
        steps: [
          {
            id: 's1',
            title: 'Publish claim lifecycle events',
            instruction:
              'Events: `claim.created`, `claim.scored`, `claim.assigned`. WebSocket broadcasts to React timeline.',
            verifyChecklist: ['Simulate 50 events/sec demo mode', 'Lag metric displayed', 'Events persisted 24h in Redis stream'],
          },
        ],
      },
    ],
  },
  {
    slug: 'secure-code-review-copilot',
    order: 10,
    phase: 4,
    phaseLabel: 'Enterprise GenAI',
    title: 'OWASP Code Review Copilot',
    company: 'Credit One Bank',
    domain: 'genai',
    stack: ['Python', 'LangChain', 'FastAPI', 'React', 'Vector DB'],
    resumeAnchor:
      'Engineered AI-driven security vulnerability detection for OWASP Top 10, PCI-DSS, and insecure coding patterns.',
    elevatorPitch:
      'Paste a PR diff; get severity-ranked findings mapped to OWASP categories with fix suggestions.',
    portfolioHighlight: 'Mirrors your banking code-review GenAI work with RAG over secure coding guides.',
    estimatedHours: 24,
    repoFolder: 'apps/p10-code-review-copilot',
    milestones: [
      {
        id: 'm1',
        title: 'Diff analyzer + rules',
        outcome: 'Static pre-checks + LLM analysis merged.',
        steps: [
          {
            id: 's1',
            title: 'Diff ingestion',
            instruction:
              'Accept unified diff or GitHub PR URL mock. Parse files/lines changed.',
            verifyChecklist: ['Multi-file diff supported', 'Secrets regex flags hardcoded keys'],
          },
          {
            id: 's2',
            title: 'OWASP-tagged findings',
            instruction:
              'LLM returns findings[] with owasp_id, severity, line, explanation, fix_snippet. Cross-check with RAG retrieval from OWASP cheat sheets.',
            verifyChecklist: ['Each finding cites OWASP category', 'Export SARIF or JSON report'],
          },
        ],
      },
      {
        id: 'm2',
        title: 'CI integration mock',
        outcome: 'GitLab/Jenkins-style status check UI.',
        steps: [
          {
            id: 's3',
            title: 'PR gate simulation',
            instruction:
              'React page mimics CI: pass/fail gate if critical findings > 0. Webhook POST stub logs payload.',
            verifyChecklist: ['Status badge updates', 'Webhook payload documented in README'],
          },
        ],
      },
    ],
  },
  {
    slug: 'multi-agent-pr-review',
    order: 11,
    phase: 4,
    phaseLabel: 'Enterprise GenAI',
    title: 'Multi-Agent PR Review Orchestrator',
    company: 'Credit One Bank',
    domain: 'genai',
    stack: ['Python', 'LangGraph-style workflow', 'FastAPI', 'React'],
    resumeAnchor:
      'Developed scalable multi-agent LLM orchestration using LangGraph and AI Agents to simulate senior engineer review workflows.',
    elevatorPitch:
      'Three agents — Security, Logic, Style — debate and produce consolidated PR review.',
    portfolioHighlight: 'Agent orchestration visible as a step graph in the UI.',
    estimatedHours: 22,
    repoFolder: 'apps/p11-multi-agent-pr',
    milestones: [
      {
        id: 'm1',
        title: 'Agent graph',
        outcome: 'Sequential + merge node with trace log.',
        steps: [
          {
            id: 's1',
            title: 'Define agent roles',
            instruction:
              'Implement planner → security → logic → style → merger. Each step append to `trace[]` with agent name and output.',
            verifyChecklist: ['UI shows live trace', 'Merger resolves conflicts explicitly', 'Total token count estimated'],
          },
        ],
      },
    ],
  },
  {
    slug: 'llm-eval-dashboard',
    order: 12,
    phase: 4,
    phaseLabel: 'Enterprise GenAI',
    title: 'LLM Evaluation Dashboard',
    company: 'Credit One Bank',
    domain: 'genai',
    stack: ['Python', 'FastAPI', 'React', 'MLflow-style metrics'],
    resumeAnchor:
      'Implemented LLM Evaluation frameworks to measure hallucination rates, groundedness, code correctness, and latency.',
    elevatorPitch:
      'Run eval suites against prompts; track hallucination, latency, groundedness over model versions.',
    portfolioHighlight: 'Closes the portfolio loop — prove you ship AND measure GenAI quality.',
    estimatedHours: 18,
    repoFolder: 'apps/p12-llm-evals',
    milestones: [
      {
        id: 'm1',
        title: 'Eval runner + charts',
        outcome: 'Batch eval dataset with comparative model charts.',
        steps: [
          {
            id: 's1',
            title: 'Eval harness',
            instruction:
              'JSON dataset of prompt, expected_keywords, grounding_doc. Score: keyword recall, LLM-judge groundedness (mock OK), latency ms.',
            verifyChecklist: ['Compare 2 model configs side-by-side', 'Export run as CSV', 'History table by run_id'],
          },
        ],
      },
    ],
  },
];

export function getProject(slug: string): Project | undefined {
  return projects.find((p) => p.slug === slug);
}

export function totalSteps(project: Project): number {
  return project.milestones.reduce((n, m) => n + m.steps.length, 0);
}

export function allStepIds(project: Project): string[] {
  return project.milestones.flatMap((m) => m.steps.map((s) => s.id));
}
