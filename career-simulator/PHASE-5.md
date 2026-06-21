# Phase 5 — AI Live Mentor (streaming chat)

## What this phase delivers

A **persistent AI mentor** in the right sidebar (desktop) and **floating chat button** (mobile):

- Streaming OpenAI responses (SSE)
- Plain-English explanations with examples
- Personalized using resume + job match context
- Conversation history saved in PostgreSQL
- **Local fallback** when `OPENAI_API_KEY` is unset (API/restaurant analogy, etc.)

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mentor/status` | OpenAI configured? |
| GET | `/api/mentor/history` | Last 40 messages |
| DELETE | `/api/mentor/history` | Clear chat |
| POST | `/api/mentor/chat/stream` | SSE stream `{ message }` |

### SSE event format

```
data: {"provider":"openai","model":"gpt-4o-mini"}
data: {"content":"Hello"}
data: {"content":" world"}
data: {"done":true}
```

---

## Mentor behavior (system prompt)

- Simple English, no unexplained jargon
- Real-world analogies (e.g. API = restaurant waiter)
- Numbered steps for tasks
- Ends with "try this next" when helpful
- Uses resume skills + job gaps from DB context

---

## Setup OpenAI

Add to `career-simulator/.env`:

```
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini
```

Restart API: `npm run dev:api`

Health check shows `"mentor": "ready"`.

---

## How to test

1. Sign in, analyze resume + job match (Phases 3–4)
2. Open sidebar on desktop (right) or tap **bot icon** on mobile
3. Try starter: **"What is an API?"**
4. Watch tokens stream in
5. Ask: **"What should I learn first from my gaps?"** — should reference your saved context

Without OpenAI key: same UI, local fallback answers.

---

## Key files

```
apps/api/src/services/mentor-prompt.ts   # system prompt + user context
apps/api/src/services/mentor-chat.ts     # OpenAI stream + local fallback
apps/api/src/routes/mentor.ts
apps/web/src/components/layout/mentor-sidebar.tsx
apps/web/src/lib/mentor-stream.ts        # SSE client
apps/web/src/components/providers/mentor-provider.tsx
```

---

## Next phase

**Phase 6 — Job simulation modules** (QA, Data Analyst, PM, AI Reviewer tasks)

Reply **"continue Phase 6"** when ready.
