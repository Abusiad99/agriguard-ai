# Knowledge corpus for the assistant

This folder holds the operator-curated source documents and their `manifest.json` (see `manifest.example.json`). It is intentionally empty in the repository: no trusted agricultural source was reachable from the environment in which the assistant was built, and documents must not be written from memory or attributed to organizations without their actual publication. See `docs/ASSISTANT_RAG.md` for the ingestion workflow.

`sources/` and `manifest.json` are git-ignored by default so that licensed material is not committed accidentally.
