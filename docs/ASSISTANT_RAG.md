# Agricultural assistant: retrieval-augmented generation

**Status: implemented and tested with fakes and test fixtures.**
- Two things have **not** been validated end to end: a live Gemini call (no API key in the build environment), and a real trusted corpus (the authoritative sources were unreachable from the build environment).
- A fresh deployment starts with an **empty knowledge base**. The assistant then says it has no relevant source. It never answers from the LLM's general knowledge.

## Architecture

```
question (+ optional diagnosis / plant, ownership checked server-side)
   │
   ├─ context: model result (status, candidates, %), user notes & follow-up answers,
   │           plant profile and recent observations      ← labelled, untrusted text
   ├─ query = question + context terms (+ Arabic→English term expansion,
   │                                     + optional Gemini query rewrite)
   ▼
HybridIndex over kb_chunks (in-process, cached; invalidated when the corpus changes)
   ├─ BM25 (always on; bilingual tokenizer with Arabic normalisation)
   ├─ cosine similarity on Gemini embeddings (only when chunks have embeddings)
   └─ reciprocal-rank fusion + crop/disease metadata boost, ≤ 2 chunks per document,
      relevance floor based on query-term coverage
   │
   ├─ no relevant chunk ───────────────► mode "no_sources" (no LLM call)
   ├─ LLM disabled / capped / failed ──► mode "retrieval_only" (passages + sources)
   ▼
Gemini (existing GeminiClient, same key and model) with:
   system rules + fenced <source id="S#">…</source> passages + <model_result>
   + <user_observations> + <history>; JSON response schema
   ▼
citations validated against the provided ids → mode "llm"
```

The existing Gemini integration is reused: one SDK client, the same `GEMINI_API_KEY` and `GEMINI_MODEL`, and the same timeout. No second provider was added.

## Storage

Migration `0003` adds:
- **`kb_documents`**: title, organization, `source_url`, `source_type` (government, university extension, research institution, pathology society, pesticide label, regulatory, AgriGuard curated record, other), language, published and revised dates, `retrieved_at`, crops, diseases, licence note, `content_sha256` (unique), and `is_active`.
- **`kb_chunks`**: text, section, token count, and optional embedding (JSON) with the embedding-model name.
- **`assistant_usage`**: per-user accounting for cost and rate limits.

No new database extension or vector service is needed. A corpus of a few thousand chunks is scored in memory. If the corpus grows to hundreds of thousands of chunks, the next step is pgvector or Postgres full-text search.

## Building the corpus (operator task)

Only add documents you have obtained from the stated organization and may use under its licence.

```bash
cd backend
# 1. Put files (txt / md / html; pdf needs the optional `pypdf` package) next to a manifest
#    — see knowledge/manifest.example.json for the required provenance fields.
python scripts/ingest_knowledge.py --manifest ../knowledge/manifest.json [--embed]
# 2. Optionally index the admin-curated disease/treatment records already in the DB
#    (cited as "AgriGuard curated record", not as an external publication):
python scripts/ingest_knowledge.py --sync-knowledge-base
python scripts/ingest_knowledge.py --list
```

**Ingestion steps:**
1. Extract the text.
2. Unicode NFKC normalisation; strip control and bidi-override characters (these can hide text from reviewers).
3. Split into sentence-aware chunks of about 900 characters with about 150 characters of overlap, keeping section headings.
4. Optional Gemini embeddings (`RETRIEVAL_DOCUMENT`).
5. Deduplicate by SHA-256 of the cleaned text.

Chemical treatments without a verified source citation are never indexed (business rule BR6).

**Arabic.** Retrieval normalises Arabic: diacritics and tatweel are removed, alef/yā'/tā' marbūṭa forms are unified, and the definite article is stripped. Arabic questions are expanded with a small Arabic→English agricultural term list, so they can match English sources lexically even when Gemini is off. Answers are written in the user's selected language and cite the sources by id.

## Safety controls

| Risk | Control |
|---|---|
| Prompt injection in retrieved documents, notes or history | Instruction-like phrases are replaced; `<` and `>` are escaped so a passage cannot close its `<source>` fence; the system rules state that fenced content is data; the output is checked for system-prompt leakage |
| Fabricated citations | Cited ids must belong to the passages actually provided; unknown `[S#]` markers are removed; answers without citations are flagged |
| Ungrounded answers | No LLM call without retrieved sources; the schema field `evidence_sufficient` is shown to the user |
| Pesticide rates | The rules forbid rates unless a pesticide-label source states them, and tell users to follow labels and local regulations |
| Access to other users' data | Diagnosis and plant context is loaded only after an ownership check (404 otherwise); the context never includes other users' data |
| Secrets | The API key stays server-side; SDK errors are logged by exception type only |
| Cost and abuse | 2,000-character questions; at most 6 history turns; at most 900 output tokens; 50 LLM answers per user per day (DB-counted); 20 requests per 5 min (app) and 10 per minute (nginx); 20 s timeout |
| Wrong language | `language` (`en` or `ar`) is validated and passed explicitly |

## API

- `POST /api/v1/assistant/chat`
  - Request: `{message, language, history[], diagnosis_id?, plant_profile_id?}`
  - Response: `{mode, answer, citations, sources[{id, title, organization, url, source_type, published_date, revised_date, section, excerpt}], evidence_sufficient, recommends_expert, notices, context_used}`
- `GET /api/v1/assistant/sources` lists the active corpus with provenance.
- `GET /api/v1/assistant/sources/{id}` returns one document's metadata.

## Tests

- `backend/tests/unit/test_rag_pipeline.py` covers chunking, tokenisation, ranking, the relevance floor, injection neutralisation, citation validation and leak detection.
- `backend/tests/unit/test_assistant_service.py` covers the three modes, LLM failure, the daily cap, input limits, context authorisation, Arabic expansion and history capping, using a fake LLM.
- `backend/tests/integration/test_assistant_api.py` runs the HTTP endpoints against SQLite with a synthetic fixture document.

The fixture text exists only for tests and is labelled as such.
