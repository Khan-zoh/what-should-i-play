# Content Embeddings Implementation Plan (Sub-plan 4) — FINAL (post-Codex debate)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans or subagent-driven-development. Steps use checkbox syntax.

**Goal:** Replace the genre-Jaccard content-similarity stand-in with sentence-transformer embeddings (all-MiniLM-L6-v2), a liked-game centroid with leave-one-out, and a grounded nearest-neighbor reason code — keeping `app/ml/` pure and torch out of CI.

**Debate provenance:** draft `2026-05-30-embeddings-draft.md` was debated with Codex (round 1: 7 objections). Final decisions below incorporate 5 concessions, 1 compromise (CI), and 1 merged fix. See the PR description for the recap table.

## Final design decisions

- **D1 (deps/CI):** `numpy` in core deps; `sentence-transformers` in a `[ml]` optional extra. CI never installs torch. `Encoder` Protocol + contract tests that FakeEncoder and the real encoder both satisfy; one `@pytest.mark.ml` real-model test auto-skipped when sentence-transformers is absent; lazy-import failure path unit-tested in CI.
- **D2 (purity):** `ml/vectors.py` (cosine, centroid, to/from bytes helpers stay in repo layer NOT ml) and `ml/content.py`: `ContentScore(similarity, nearest_slug, nearest_name)`, `HighRatedItem(game_id, slug, name, vector)`, `content_scores(candidate_vecs: dict[int, np.ndarray], high_rated: list[HighRatedItem]) -> dict[int, ContentScore]` with **leave-one-out** (a candidate that is itself high-rated is excluded from its own centroid and nearest-neighbor). Similarity = `max(0.0, cosine(candidate, loo_centroid))`. numpy allowed in ml/ (purity guard forbids only sqlalchemy/fastapi/app-layers).
- **D3 (storage/lifecycle):** `GameEmbeddingRepository` (upsert/get_all/missing_game_ids) storing float32 `.tobytes()`. Composite revision key in the `model_name` column: `f"{model_short}|t{TEXT_TEMPLATE_VERSION}"` = `"all-MiniLM-L6-v2|t1"`. Input text: `f"{name} - {summary or ''} | tags: {', '.join(sorted(genres+themes))}"`. Dedicated `POST /api/embeddings/rebuild` (`?force=true` re-embeds all) returning `{model, attempted, embedded, skipped_existing, failed:[{game_id, error}]}`. Sync untouched. Onboarding ConnectStep fires rebuild fire-and-forget after successful import.
- **D4 (scoring):** `score_candidates(profile, candidates, weights, content: dict[int, ContentScore] | None = None)`. Request-level all-or-nothing: service passes `content` only when centroid computable AND every candidate has a vector; then content term = `ContentScore.similarity` and reason code `SIMILAR_TO_HIGH_RATED_GAME:<slug>` (when nearest exists and similarity >= 0.35). Otherwise `content=None` → existing genre-Jaccard path with `SIMILAR_TO_HIGH_RATED:<genre>`. model_version = `heuristic-v1` iff content channel active, else `heuristic-v0`. Embedding revision string included in feature_hash payload when v1.
- **D5 (explanations):** `explain()` handles `SIMILAR_TO_HIGH_RATED_GAME:<slug>` → "is similar to <Slug Humanized>" (slug: dashes→spaces, title case).

## Tasks
1. Deps + config: numpy core, `[ml]` extra, `Settings.embedding_model_name`, constants module for template version.
2. `ml/vectors.py` (cosine, centroid) + tests (zero vector, orthogonal, identical, empty centroid).
3. `ml/content.py` (ContentScore/HighRatedItem/content_scores, leave-one-out, deterministic ties) + tests.
4. Heuristic: optional `content` channel + new reason code + tests (channel overrides Jaccard; LOO; threshold; determinism).
5. `explanations.explain` handles the new code + tests.
6. `GameEmbeddingRepository` + tests (bytes round-trip via numpy, missing detection, upsert idempotent).
7. `EmbeddingService`: `Encoder` Protocol, `build_input_text`, `embed_missing(force)` report, lazy real-encoder factory + clear ImportError message; FakeEncoder contract tests + `@pytest.mark.ml` real-model test; lazy-import failure test.
8. `POST /api/embeddings/rebuild` + tests.
9. `recommender_service` wiring: load embeddings for revision, build HighRatedItems (enjoyment>=4 + vector), all-or-nothing switch, model_version bump, feature_hash includes revision + tests.
10. Frontend: `postEmbeddingsRebuild()` in api.ts; ConnectStep fires it after successful import (fire-and-forget); build+test.
11. Verify all + install `[ml]` locally + live smoke (rebuild 23 games, rate one Loved, confirm v1 + SIMILAR_TO_HIGH_RATED_GAME code) + README + memory + PR.
