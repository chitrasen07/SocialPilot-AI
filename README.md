# SocialPilot AI

AI customer conversation platform for social media. Instagram (via official Meta APIs) is the
first channel.

Modular monolith: React + TypeScript (Vite) frontend, FastAPI backend, PostgreSQL + pgvector,
Redis.

```text
frontend/   React 19, TypeScript, Vite, Tailwind CSS, React Router, Firebase Auth
backend/    FastAPI, SQLAlchemy 2 (async), Alembic, Redis client
  app/api/            HTTP routes
  app/core/           settings, errors, logging / request IDs, Firebase, token encryption
  app/db/             engine and declarative base
  app/models/         SQLAlchemy models
  app/services/       business logic
  app/integrations/   external platforms (Instagram provider, webhook parsing)
  app/workers/        background worker and queue
  alembic/            database migrations
  tests/
```

## Quick start (Docker)

```bash
cp .env.example .env        # optional; defaults work if ports 5432/6379/8000/5173 are free
docker compose up --build
```

| Service  | URL                                         |
| -------- | ------------------------------------------- |
| Frontend | http://localhost:5173                       |
| API      | http://localhost:8000/api/health/ready      |
| API docs | http://localhost:8000/api/docs (non-prod)   |

If a port is already in use, change `POSTGRES_PORT`, `REDIS_PORT`, `BACKEND_PORT` or
`FRONTEND_PORT` in `.env`.

After changing frontend dependencies, rebuild with `docker compose up --build -V` so the
container's `node_modules` volume is refreshed.

The backend container applies migrations (`alembic upgrade head`) before starting. In
production, run migrations once as a release step instead.

## Running checks

```bash
docker compose exec backend python -m pytest
docker compose exec backend ruff check .
docker compose exec backend ruff format --check .

cd frontend && npm run build   # type check + production build
```

## Running without Docker

Requires Python 3.12+, Node 22+, and reachable Postgres (with the `vector` extension available)
and Redis. The backend reads the repo-root `.env`.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

python -m app.workers.worker   # in a second terminal

cd frontend
npm install
npm run dev                  # proxies /api to API_PROXY_TARGET (default http://localhost:8000)
```

## API conventions

- All routes are under `/api`.
- Errors always use `{"error": {"code": "...", "message": "...", "details"?: ...}}`. Internal
  exception details are never returned to clients.
- Every response carries an `x-request-id` header (an incoming one is reused), and it appears in
  every JSON log line for that request.
- `GET /api/health` is liveness. `GET /api/health/ready` checks Postgres, pgvector and Redis,
  and returns `503` when any are unavailable.

## Authentication

Firebase Authentication owns identity (Google and email/password); PostgreSQL owns application
data. The frontend sends the Firebase ID token as `Authorization: Bearer <token>`; the backend
verifies it with Firebase Admin and requires a verified email.

- `POST /api/auth/sync` creates the user on first login (with a personal organization and an
  owner membership) and updates `last_login_at` afterwards. It is safe under concurrent calls.
- Organization-scoped endpoints take the organization from the `{organization_id}` path segment
  or the `X-Organization-Id` header, and always check membership server-side.
- Roles, lowest to highest: `viewer` < `agent` < `admin` < `owner`. Use
  `Depends(require_role(Role.ADMIN))` from `app/api/deps.py` for role-gated operations.

Firebase Console setup:

1. Create a project and a Web app; copy its config into the `VITE_FIREBASE_*` variables.
2. Authentication > Sign-in method: enable **Email/Password** and **Google**.
3. Authentication > Settings > Authorized domains: add every domain that serves the frontend
   (`localhost` is included by default).
4. Project settings > Service accounts: generate a private key and set `FIREBASE_PROJECT_ID`,
   `FIREBASE_CLIENT_EMAIL` and `FIREBASE_PRIVATE_KEY` (backend only).

Without Firebase Admin credentials the API still starts in development, and protected endpoints
return `503 AUTH_NOT_CONFIGURED`. In production, startup fails instead. Tests mock Firebase and
run against a separate `<database>_test` database.

## Instagram integration

Uses the official **Instagram API with Instagram Login** (Business/Creator accounts). All
Meta-specific code lives in `backend/app/integrations/instagram/`; endpoints, API version,
scopes and webhook fields are settings (`META_*`), so Meta changes don't require code edits.

**Connecting (OAuth):** `POST /api/instagram/connect` (admin+) stores a single-use state in
Redis (10 min TTL) bound to the user and organization, sets an HttpOnly cookie that binds the flow
to the browser, and returns Instagram's authorization URL. `GET /api/instagram/callback` consumes
the state, re-checks the caller's role, exchanges the code server-side for a long-lived token,
subscribes the account to webhooks, and redirects to `/integrations` with a result code.
Tokens are Fernet-encrypted (`TOKEN_ENCRYPTION_KEYS`) and never returned by the API. An Instagram
account can be actively connected to only one organization. The worker refreshes tokens before
they expire and flags accounts that need re-authorization.

**Webhooks:** `GET /api/webhooks/instagram` answers Meta's verification handshake.
`POST /api/webhooks/instagram` verifies `X-Hub-Signature-256`, stores the raw delivery in
`webhook_deliveries` (identical bodies are de-duplicated), pushes its ID to Redis and returns.
The **worker** (`python -m app.workers.worker`, the `worker` Compose service) claims deliveries
atomically, extracts direct messages and comments into organization-scoped `instagram_events`
(idempotent on Meta's message/comment ID), clears the raw payload, and retries failures with
backoff. A sweeper re-enqueues anything the queue lost, so Redis is never the source of truth.

## Customers, conversations and memory

In the same transaction that stores a delivery's events, the worker normalizes each direct
message (`app/services/normalization.py`):

```text
instagram_events → customer → conversation → message
```

- **Customer:** one per (organization, Instagram account, Instagram-scoped user ID). Instagram
  message webhooks don't include usernames, so new customers show their Instagram user ID until
  profile data is available.
- **Conversation:** a customer has at most one *active* (`open` or `pending`) conversation. A
  message after the conversation was closed starts a new one, and closed ones remain as history.
- **Message:** unique per (organization, Meta message ID). Echoes of messages the business sent
  are stored with `sender_type = "business"`. Unsent messages have their content removed.

Idempotency and concurrency are enforced by database constraints, not by read-then-write checks.
The constraints are the customer unique key, a partial unique index on the active conversation,
and the message unique key, all used with `INSERT … ON CONFLICT`. Redelivered or concurrently
processed events therefore never create duplicates. Composite foreign keys guarantee that a
conversation, message or memory always belongs to the same organization as its customer.
Comments are still stored as events but are not normalized yet.

**Customer memory** (`customer_memories`, `app/services/memory.py`) stores persistent facts,
preferences and interests per customer, with an optional 768-dimension pgvector embedding.
`search_customer_memory(organization_id, customer_id, query_embedding, limit)` does an exact
cosine-distance search scoped to one customer, so results are deterministic. Saving a memory
does not call an LLM. Phase 5 embeds the current message when it searches these memories for a draft.

**API** (organization from `X-Organization-Id`; viewer+ can read, agent+ can modify):

| Endpoint | Notes |
| --- | --- |
| `GET /api/customers` | `search`, `limit` (≤100), `offset`; sorted by most recent activity |
| `GET /api/customers/{id}` | Profile plus recent conversations |
| `GET/POST /api/customers/{id}/memories`, `DELETE …/memories/{memory_id}` | Memory management |
| `GET /api/conversations` | `status`, `customer_id`, `limit` (≤100), `offset`; includes the latest message |
| `GET /api/conversations/{id}` | Conversation, customer and its latest messages |
| `PATCH /api/conversations/{id}` | `{"status": "open" \| "pending" \| "closed"}` |
| `GET /api/conversations/{id}/messages` | `limit` (≤100, default 50), `before` cursor |

Paged lists return `has_more`. Messages come back oldest-first, with `next_cursor` for older
pages. Resources from another organization return `404`. The frontend shows these in `/inbox`
(read-only; replies aren't sent from SocialPilot yet), `/customers`, `/customers/{id}` and
`/settings`.

Phase 4 tests and local development do **not** require `META_APP_ID`, `META_APP_SECRET` or
`META_REDIRECT_URI`. Normalization tests feed deterministic webhook JSON into the same
`record_delivery` → `process_delivery` path the worker uses. Real Meta credentials remain
deferred until live Instagram OAuth/webhook testing.

### Meta Developer Console setup (manual)

Meta's requirements change; confirm each step against the current Meta documentation.

1. Create a Meta app of type **Business** and add the **Instagram** product, then open
   **API setup with Instagram login**.
2. Copy the **Instagram app ID** and **Instagram app secret** into `META_APP_ID` /
   `META_APP_SECRET`.
3. Under Business login settings, add your OAuth redirect URL, e.g.
   `https://<public-host>/api/instagram/callback`, and set `META_REDIRECT_URI` to exactly that.
   Set `FRONTEND_URL` to the same origin, and open the app in the browser through that origin
   (the OAuth cookie is bound to it).
4. Configure webhooks: callback URL `https://<public-host>/api/webhooks/instagram`, verify
   token = `META_WEBHOOK_VERIFY_TOKEN`, and subscribe to the `comments` and `messages` fields.
5. While the app is in development mode, only accounts with a role on the app (or added as
   Instagram testers) can authorize it. Going live requires Meta App Review for the requested
   permissions (`META_SCOPES`) and Business Verification.

For local testing, expose the frontend dev server (which proxies `/api`) through an HTTPS tunnel
and add the tunnel hostname to `VITE_ALLOWED_HOSTS`.

Disconnecting in SocialPilot deletes the stored token and stops processing; to revoke the app
itself, the account owner removes it in Instagram's settings.

## AI engine

Phase 5 reads a stored customer message and returns a **draft**. It does not send Instagram
messages, publish comments, or call Meta's send API.

```text
Customer message
  → analysis (language, intent, sentiment, emotion, purchase intent)
  → relevant customer memories
  → recent conversation
  → reply generation
  → guardrails
  → AI draft in the inbox
```

Obvious messages are classified with local rules so a model is not called for every label.
Ambiguous text uses one structured call. The result is validated before it is stored. A second
analysis of the same message returns the stored row.

`AIProvider` is the only interface the orchestrator uses. `AI_PROVIDER=mock` is deterministic and
is what tests use. `AI_PROVIDER=gemini` uses the official `google-genai` SDK (`google-genai`,
model `GEMINI_MODEL`, default `gemini-2.5-flash`). Without `GEMINI_API_KEY` the process still
starts; AI routes return `AI_NOT_CONFIGURED`. The key stays in backend environment variables. It
is not stored in the database and is not exposed to the frontend.

Other backend settings, all optional: `EMBEDDING_MODEL` (default `gemini-embedding-001`),
`AI_TEMPERATURE`, `AI_MAX_OUTPUT_TOKENS`, `AI_TIMEOUT_SECONDS`, `AI_MAX_CONTEXT_MESSAGES`,
`AI_MEMORY_TOP_K`, `AI_REQUESTS_PER_MINUTE`, `AI_MAX_RETRIES`. See `.env.example`.

Embeddings for memory search are 768-dimensional, matching `customer_memories`. Tests use a
deterministic mock embedding. Gemini embeddings request `output_dimensionality=768`.

| Endpoint | Who | Notes |
| --- | --- | --- |
| `POST /api/ai/analyze-message` | viewer+ | `{"message_id": "..."}` |
| `POST /api/ai/generate-reply` | agent+ | Draft only. `sent` is always false |
| `GET /api/ai/messages/{message_id}` | viewer+ | Stored analysis and latest draft |
| `GET/PATCH /api/ai/settings` | admin+ | Limits and enablement. No API key |

Another organization's message returns `404`. Rate limits return `429` (`AI_RATE_LIMITED`).
Provider timeouts return `504` (`AI_PROVIDER_TIMEOUT`). A blocked draft returns `422`
(`AI_GUARDRAIL_BLOCKED`) and is stored without the unsafe text.

Replies do not confirm stock, prices, orders, refunds, or payments unless that information is
already in the conversation or customer memory. The inbox shows analysis and a draft composer
with regenerate and edit. There is no send button.

`auto_analysis_enabled` is stored on the organization. Incoming webhooks are not analyzed
automatically in this phase.

Phase 5 tests do **not** require Gemini or Meta credentials.

## Knowledge base

Phase 6 adds an organization-scoped knowledge base. A draft can use business documents in
addition to customer memory and the recent conversation. Retrieved text is reference data.
It is not instructions, and it is not treated as proof that the business information is correct.

```text
Upload → validate → store → extract → clean → chunk → embed → pgvector
Customer message → relevant chunks → prompt → guardrails → AI draft + citations
```

Supported files: PDF, DOCX, TXT, and CSV, up to `KNOWLEDGE_MAX_FILE_SIZE_MB` (default 10).
Scanned PDFs are not read; this phase does not run OCR. A PDF with no text layer fails
ingestion instead of becoming an empty document.

Chunks target about 600 words with an 80-word overlap (`KNOWLEDGE_CHUNK_SIZE`,
`KNOWLEDGE_CHUNK_OVERLAP`). Embeddings reuse the Phase 5 provider and stay 768-dimensional.
Search uses cosine distance, the same metric as customer memory, and drops chunks farther than
`KNOWLEDGE_RETRIEVAL_MAX_DISTANCE` (default 0.5, where 0 is identical). Only documents with
status `ready` are searchable. Tests use the deterministic mock embedding and do not call Gemini.

Uploads are saved under `KNOWLEDGE_STORAGE_PATH` with generated ids, not the original filename.
The API does not return that path. Ingestion runs on the existing Redis worker. Deleting a
document removes its file and its chunks.

| Endpoint | Who |
| --- | --- |
| `POST /api/knowledge/documents` | admin+ multipart upload |
| `GET /api/knowledge/documents` | viewer+ |
| `GET /api/knowledge/documents/{id}` | viewer+ |
| `DELETE /api/knowledge/documents/{id}` | admin+ |
| `POST /api/knowledge/documents/{id}/reprocess` | admin+ |
| `POST /api/knowledge/search` | viewer+ |

`POST /api/ai/generate-reply` attaches `sources` from the chunks it actually retrieved.
Analysis does not search the knowledge base. Nothing is sent to Instagram.

The UI is `/knowledge-base`. Admins can also set knowledge retrieval, top K, and the distance
threshold under Settings. API keys and the storage path are not editable there.

Phase 6 tests do **not** require Gemini or Meta credentials.

## Brand control and human review

Phase 7 adds organization brand settings and a draft review workflow on top of the existing
AI provider, memory, and knowledge base. A draft is still not sent to Instagram.

```text
Message → analysis → memory + conversation + knowledge
        → brand personality and reply policy → AI provider
        → guardrails → risk → draft, review, edit, approve, or reject
```

Admins set personality, brand voice, custom instructions, preferred and forbidden words, emoji
policy, response length, and language mode under Settings. `auto` follows the customer's
language. Customer messages and uploaded documents stay untrusted: they cannot override safety
or brand rules.

Guardrails are deterministic. They block secret disclosure, system-prompt disclosure, and
claims that a refund, payment, order, or delivery already happened. Forbidden words, unsupported
prices, and emoji-policy misses keep the draft and mark it for review instead of silently
rewriting it. Risk is `low`, `medium`, or `high`. High means a person should look, not that the
customer is correct. Refunds, payment disputes, legal complaints, and safety concerns are
escalated when those review settings are on. They default to on.

Draft status stays `generated` for an ordinary low-risk draft, so existing clients keep working.
Other states are `review_required`, `edited`, `approved`, `rejected`, and `expired`. A rejected
draft cannot be approved until someone edits it into a version that passes guardrails. Approving
records who reviewed it and when. `sent` stays false.

| Endpoint | Who |
| --- | --- |
| `GET /api/ai/review-queue` | viewer+ |
| `POST /api/ai/drafts/{id}/approve` | agent+ |
| `POST /api/ai/drafts/{id}/edit` | agent+ |
| `POST /api/ai/drafts/{id}/reject` | agent+ |
| `POST /api/ai/drafts/{id}/escalate` | agent+ |

The inbox shows risk, status, sources, and guardrail flags. The review queue is `/review`.
Brand settings are stored on `ai_settings`. There is no new API key and no new environment
variable for this phase.

AI drafts are not automatically sent.

## Customer intelligence and analytics

Phase 8 adds a profile above each customer, memory suggestions, segments, daily analytics,
and draft feedback. A draft is still not sent to Instagram.

```text
Message → analysis → memory suggestion (pending)
        → customer profile and segments
        → reply prompt includes the profile as untrusted context
        → human approves a suggestion before it becomes memory
        → approve, edit, or reject stores feedback
```

Profiles use conversation messages, approved memories, and stored analysis. They do not store
birthdays, age, religion, health, addresses, or contact details. Suggestions stay pending until
an agent approves or rejects them. Approving writes a normal customer memory. Segments describe
shopping behavior, not demographics.

Reply context order stays fixed: system instructions, brand settings, business knowledge,
customer memory, customer intelligence, recent conversation, then the current message.
Customer text never enters the system instruction block. Knowledge stays labeled
`BUSINESS KNOWLEDGE — UNTRUSTED REFERENCE DATA`.

| Endpoint | Who |
| --- | --- |
| `GET /api/customers/{id}/intelligence` | viewer+ |
| `GET /api/customers/{id}/memory-suggestions` | viewer+ |
| `POST /api/memory-suggestions/{id}/approve` | agent+ |
| `POST /api/memory-suggestions/{id}/reject` | agent+ |
| `GET /api/analytics/overview` | viewer+ |
| `GET /api/analytics/customers` | viewer+ |
| `GET /api/analytics/ai-performance` | viewer+ |
| `POST /api/ai/drafts/{id}/feedback` | agent+ |

The analytics page is `/analytics`. Feedback is stored for a later training step. This phase
does not fine-tune a model and does not call Instagram.

## Automation

Phase 9 adds organization rules that prepare drafts, open tasks, or notify teammates.
A rule never sends an Instagram message.

```text
Customer event → matching enabled rules → draft, task, or notification
```

Triggers are message received, sentiment, intent, customer created, and segment changed.
Conditions are exact labels such as `pricing_question`, `negative`, or `high_intent_buyer`.
`generate_draft` calls the existing AI pipeline: brand settings, knowledge, memory,
customer intelligence, and guardrails. Disabled rules do nothing.

| Endpoint | Who |
| --- | --- |
| `GET /api/automation/rules` | viewer+ |
| `POST /api/automation/rules` | admin+ |
| `PATCH /api/automation/rules/{id}` | admin+ |
| `DELETE /api/automation/rules/{id}` | admin+ |
| `GET /api/tasks` | viewer+ |
| `POST /api/tasks` | agent+ |
| `PATCH /api/tasks/{id}` | agent+, assigned task or admin |
| `GET /api/notifications` | viewer+, own notifications |
| `POST /api/notifications/{id}/read` | viewer+, own notification |

The builder is `/automation`. The task list is `/tasks`. The notification bell shows the unread count.

AI drafts are not automatically sent.

## Channels

Phase 10 adds WhatsApp, Messenger, email, and a website chat widget beside Instagram.
Every channel writes the same customer, conversation, and message rows and uses the existing
AI pipeline. A draft is prepared for review. Nothing is sent to the customer.

```text
Inbound message → channel provider → normalizer → conversation → analysis → draft
```

Instagram continues to arrive on `POST /api/webhooks/instagram`. Other channels use a signed
webhook on `POST /api/channels/webhook/{channel_id}`. The website widget uses
`POST /api/channels/webchat/{channel_id}/messages` and shows the visitor their own messages.

| Endpoint | Who |
| --- | --- |
| `GET /api/channels` | viewer+ |
| `GET /api/channels/settings` | viewer+ |
| `POST /api/channels/connect` | admin+ |
| `PATCH /api/channels/{id}` | admin+ |
| `POST /api/channels/webhook/{channel_id}` | signed webhook |
| `GET /api/analytics/channels` | viewer+ |

The inbox is `/inbox`, with channel, status, and priority filters. Channel status is `/integrations`.
The public chat page is `/widget`. Webhook secrets are encrypted and are not returned by the
channel list.

AI drafts are not automatically sent.

## Engagement intelligence

Phase 11 reads messages, approved memories, and knowledge documents. It records conversation
stage, lifecycle, lead score, and product names that already appear in the knowledge base.
Draft scoring is deterministic. Review feedback is counted. No model is fine-tuned, and no
message is sent.

| Endpoint | Who |
| --- | --- |
| `GET /api/intelligence/dashboard` | viewer+ |
| `GET /api/intelligence/customers/{id}` | viewer+ |

The dashboard is `/intelligence`. Customer profiles show lifecycle stage, lead score, buying
probability, churn risk, and the recommended next review action.

AI drafts are not automatically sent.

## Secrets

All secrets live in environment variables on the backend. `.env` is gitignored. Firebase Admin
credentials, Meta app secrets, Instagram access tokens, and AI keys must never be exposed to the
frontend.
