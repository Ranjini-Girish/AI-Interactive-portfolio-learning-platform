export type Job = {
  company: string;
  location: string;
  role: string;
  period: string;
  highlights: string[];
};

export const contact = {
  email: 'Racgowda18@gmail.com',
  phone: '619-736-0266',
};

export const summary = [
  '8+ years building Python, AI/ML, and GenAI systems across banking, insurance, and retail.',
  'Production LLM apps with Claude, OpenAI, LangChain, LangGraph, and AWS SageMaker.',
  'Expertise in RAG, multi-agent orchestration, secure code review, and LLM evaluation.',
];

export const skillGroups: Record<string, string[]> = {
  'AI / ML & GenAI': [
    'PyTorch',
    'RAG',
    'LLM Agents',
    'RLHF',
    'SFT',
    'Prompt Engineering',
    'LangChain',
    'LangGraph',
  ],
  'Backend & APIs': ['Python', 'FastAPI', 'Flask', 'Django', 'Spring Boot', 'REST', 'Microservices'],
  'Data & Storage': ['Pandas', 'NumPy', 'PostgreSQL', 'MongoDB', 'Redis', 'ETL'],
  'MLOps & Cloud': ['MLflow', 'CI/CD', 'Docker', 'Kubernetes', 'AWS SageMaker', 'ECS', 'Lambda'],
};

export const experience: Job[] = [
  {
    company: 'Credit One Bank',
    location: 'Las Vegas, NV',
    role: 'Gen AI Engineer',
    period: 'Dec 2024 – Present',
    highlights: [
      'Enterprise GenAI for secure code review, compliance validation, and developer productivity.',
      'RAG pipelines with Pinecone, LangChain, and semantic search for code intelligence.',
      'Multi-agent LLM orchestration with LangGraph for PR validation workflows.',
      'LLM eval frameworks for hallucination, groundedness, and latency benchmarks.',
    ],
  },
  {
    company: 'Pacific Specialty Insurance',
    location: 'Anaheim, CA',
    role: 'AI/ML Engineer',
    period: 'Aug 2023 – Nov 2024',
    highlights: [
      'End-to-end ML pipelines for claims risk, fraud detection, and policy optimization.',
      'RAG systems with FAISS for policy document and claims history retrieval.',
      'Real-time event-driven pipelines with Redis for low-latency processing.',
      'MLOps with CI/CD, model versioning, and MLflow-style monitoring.',
    ],
  },
  {
    company: 'Columbia Sportswear',
    location: 'Portland, OR',
    role: 'ML Engineer',
    period: 'May 2021 – Jul 2023',
    highlights: [
      'Hybrid recommendation systems (collaborative + content-based filtering).',
      'Demand forecasting and inventory optimization with regression models.',
      'Flask REST APIs serving personalized recommendations with caching.',
      'PostgreSQL and MongoDB for retail analytics at scale.',
    ],
  },
  {
    company: 'Willamette Valley Bank',
    location: 'Salem, OR',
    role: 'ML Engineer',
    period: 'Mar 2019 – Apr 2021',
    highlights: [
      'Customer segmentation and churn prediction with scikit-learn.',
      'FastAPI data services and large-scale ETL with Pandas.',
      'SQL optimization and feature engineering for banking analytics.',
    ],
  },
  {
    company: 'Zenith Insurance',
    location: 'Los Angeles, CA',
    role: 'Python Developer',
    period: 'Sept 2017 – Feb 2019',
    highlights: [
      'Django + Angular full-stack applications with REST APIs.',
      'AWS EC2/SQS async processing and Jenkins CI/CD pipelines.',
    ],
  },
];
