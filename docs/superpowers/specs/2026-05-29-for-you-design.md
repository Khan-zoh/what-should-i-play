# Sub-plan 3 — Heuristic "For You" v0 + Telemetry (Design Spec)

**Date:** 2026-05-29
**Status:** Approved (pending spec review)
**Depends on:** Foundation, 2a (library import), 2b (ratings + preferences), 2c (onboarding). Builds toward 4 (embeddings), 7 (eval harness), 8 (reranker).

---

## 1. Goal

A "For You" surface that ranks games **the user already owns** ("what should I play next from my library") using a deterministic heuristic, explains each pick with grounded reason codes, and logs the full impression→interaction telemetry that the later offline-eval harness and personal reranker depend on. This sub-plan also establishes the pure `ml/` package boundary that the entire ML story rests on.

This is **v0**: no embeddings, no learned model, no buyable-game catalog. The candidate set is the owned library; the scorer is a hand-weighted sum over signals already present in the database.

## 2. Scope

**In scope**
- Persist IGDB genres/themes as `GameTag` rows during Steam sync (precursor — the heuristic needs genre data).
- A pure `ml/` package: dataclasses + a deterministic heuristic scorer + default weights.
- A `recommender_service` that loads candidates through a source-agnostic `CandidateSource` interface, builds features, calls `ml/`, and writes telemetry.
- `recommendation_events` repository + `GET /api/for-you` + interaction endpoints (click / dismiss-with-reason / start-playing).
- A `/for-you` frontend page with reason-code explanations and interaction controls.

**Out of scope (later sub-plans)**
- Sentence-transformer embeddings / content cosine (sub-plan 4) — v0 uses genre Jaccard as the content-similarity stand-in.
- Buyable-game catalog ingestion + buy recommendations.
- Mood clusters / quiz (sub-plan 6).
- Personal reranker — Ridge/LightGBM (sub-plan 8).
- LLM-rewritten explanations (sub-plan 9) — v0 uses templated sentences.
- Result caching, price signals, per-game session-length signals.

## 3. Precursor: persist genres/themes as tags

The current `library_sync._upsert_game` discards the genres/themes that `IgdbClient` already fetches; `GameTag` is empty. Change:
- `library_sync` writes each IGDB genre as `GameTag(kind="genre", tag=<name>)` and each theme as `GameTag(kind="theme", tag=<name>)` for the game, replacing any existing tags of those kinds on re-sync (idempotent).
- `GameRepository` (or a new `GameTagRepository`) gains a `replace_tags(game_id, kind, tags)` method so the orchestrator stays ORM-free.
- Backfill: re-running the existing Steam sync re-queries IGDB and populates tags for the 23 owned games — no separate backfill job.

`GameTag` columns in use: `game_id`, `tag` (the genre/theme name), `kind` (`"genre"` | `"theme"`).

## 4. The `ml/` package (pure)

`backend/app/ml/` — imports neither SQLAlchemy nor FastAPI nor any I/O.

### 4.1 `ml/types.py` — dataclasses (frozen)
- `GameFeatures`: `game_id: int`, `slug: str`, `name: str`, `genres: frozenset[str]`, `themes: frozenset[str]`, `critic_score: float | None`, `hours_played: float`, `status: str | None`, `user_enjoyment: int | None`, `release_year: int | None`.
- `UserProfile`: `liked_genres: frozenset[str]`, `disliked_genres: frozenset[str]`, `liked_types: frozenset[str]`, `high_rated_genres: frozenset[str]` (union of genres from games rated ≥4), `session_length_pref: str`, `difficulty_pref: str`.
- `ScoredCandidate`: `game_id: int`, `score: float`, `reason_codes: list[str]`, `contributions: dict[str, float]` (per-signal breakdown, for the "Why?" debug surface and future eval).

### 4.2 `ml/weights.py`
Default grouped weights as a frozen dataclass `HeuristicWeights(personal_match: float, content_similarity: float, quality: float, backlog_boost: float)` with documented defaults. Hand-set, normalized to feature scales; tuning is deferred to the eval sub-plan.

### 4.3 `ml/heuristic.py`
`score_candidates(profile: UserProfile, candidates: list[GameFeatures], weights: HeuristicWeights) -> list[ScoredCandidate]`:
- Computes per-candidate signal terms (all in [0,1] before weighting):
  - **personal_match**: `(#liked genres present − #disliked genres present) ` normalized; liked types add a small bonus.
  - **content_similarity**: Jaccard(candidate.genres, profile.high_rated_genres).
  - **quality**: `critic_score / 100` (0 if `None`).
  - **backlog_boost**: `OWNED_AND_UNPLAYED` if `hours_played < 1.0`; `BACKLOG_PRIORITY` if `status in {backlog, installed}`.
- Final score = weighted sum of the terms.
- **Exclusions** (candidate dropped entirely): `status in {hidden, abandoned, not_interested}`.
- **Down-rank** (not dropped): `status == completed` and `user_enjoyment is not None and user_enjoyment <= 2` apply a negative term so they sink.
- Emits deterministic `reason_codes` (see 4.4). Returns candidates sorted by score descending; ties broken by `game_id` for determinism.
- Pure and total: same inputs → same outputs, no randomness, no clock, no I/O.

### 4.4 reason_codes (v0 set)
`MATCHES_LIKED_GENRE:<genre>` (per matched liked genre, capped), `SIMILAR_TO_HIGH_RATED:<genre>` (top shared high-rated genre), `HIGH_CRITIC_SCORE` (critic ≥ 80), `OWNED_AND_UNPLAYED`, `BACKLOG_PRIORITY`. At least one code is always present (fallback `IN_YOUR_LIBRARY` if nothing else fires) so explanations never render empty.

## 5. Orchestration + telemetry

### 5.1 `services/recommender_service.py`
- `CandidateSource` protocol: `candidates(session) -> list[GameFeatures]`. v0 implementation `OwnedLibraryCandidateSource` joins library_entries + games + tags + ratings + user_game_state into `GameFeatures`. The interface lets a future `BuyableCandidateSource` plug in without changing the scorer or service shape.
- `RecommenderService.recommend(limit) -> list[Recommendation]`:
  1. Build `UserProfile` from `PreferencesRepository` + the user's ≥4-rated games' genres.
  2. Get candidates from the source.
  3. `score = ml.heuristic.score_candidates(profile, candidates, weights)`; take top `limit`.
  4. For each, write a `recommendation_events` impression row (`surface="for_you"`, `rank`, `score`, `reason_codes`, `model_version="heuristic-v0"`, `feature_hash`, `filters_applied`, `cache_hit=False`, `abstention_path="heuristic"`, `explanation_variant="templated"`).
  5. Return `Recommendation` DTOs (game display fields + `event_id` + reason_codes + templated explanation).
- `feature_hash`: stable hash of the profile + candidate feature inputs (for reproducibility/repro-debugging; not used for caching in v0).
- **No result caching in v0** — recompute per request (trivial at this scale). `cache_hit` is always `False`.

### 5.2 `RecommendationEventRepository`
- `create_impressions(rows) -> list[int]` (returns event ids).
- `get(event_id) -> RecommendationEvent | None`.
- `mark_clicked(event_id)`, `mark_dismissed(event_id, reason)`, `mark_started_playing(event_id)` — each sets the corresponding timestamp column; idempotent (setting an already-set timestamp is a no-op overwrite).

### 5.3 Explanations
A pure templating function in `ml/explanations.py` maps reason_codes → one sentence (e.g. `OWNED_AND_UNPLAYED` + `MATCHES_LIKED_GENRE:RPG` → "An unplayed RPG in your library you might enjoy."). It is pure and unit-tested. **The backend is the single source of truth**: the service computes `explanation` from the reason_codes and returns it on each card. The frontend renders the returned `explanation` and the raw `reason_codes` as-is — no client-side templating, so there is no duplicated logic to keep in sync.

## 6. API

All under the existing thin-route + repository pattern, using the shared `get_db_session`.

- `GET /api/for-you?limit=20` → `{ items: ForYouItem[] }`. Runs the recommender, **logs impressions**, returns each card with: `event_id`, `game_id`, `name`, `slug`, `cover_url`, `genres: string[]`, `critic_score`, `hours_played`, `status`, `reason_codes: string[]`, `explanation: string`, `score`, `model_version`.
- `POST /api/recommendations/{event_id}/click` → 200; sets `clicked_at`. 404 if event unknown.
- `POST /api/recommendations/{event_id}/dismiss` body `{reason}` → 200; sets `dismissed_at` + `dismiss_reason`. Validates reason against `{too_long, wrong_genre, too_expensive, wrong_platform, already_played_elsewhere, not_interested}` (422 otherwise). 404 if unknown.
- `POST /api/recommendations/{event_id}/start-playing` → 200; sets the game's `UserGameState.status = "currently_playing"` **and** the event's `started_playing_at`. 404 if unknown.

New router `app/api/recommendations.py` (registered in `main.py`).

## 7. Frontend "For You" page

- Route `/for-you` under `AppShell`; add a "For You" nav link.
- On load: `GET /api/for-you`. Render a responsive list/grid of cards: cover, name, genre tag chips, critic score, hours, the `explanation` sentence, and a **"Why?"** expander showing the raw `reason_codes`.
- Per-card controls:
  - **Start playing** → `POST .../start-playing`; optimistic, marks the card and removes/badges it.
  - **Dismiss** → opens a small reason `Select`; on choose, `POST .../dismiss {reason}`; optimistically removes the card.
  - Card body click → `POST .../click` (fire-and-forget; non-blocking).
- States: loading; error; **cold-start** (fewer than a threshold of rated games) shows an inline "Rate more games to personalize" note above results; **empty library** reuses the "Import from Steam" empty-state pattern.
- Small dev indicator: "ranked by: heuristic-v0" (from `model_version`).
- Interaction posts are best-effort: failures are swallowed (telemetry must never block the UI), except start-playing which rolls back its optimistic status change on failure.

## 8. Data flow

App → `GET /api/for-you` → service builds profile + candidates → `ml.heuristic` ranks → impressions written → cards returned with `event_id`s. User interactions → POST to the matching endpoint → event row updated (and status updated for start-playing). Re-loading the page recomputes and logs fresh impressions (expected telemetry behavior).

## 9. Error handling

- Empty library or no preferences → recommender returns `[]`; page shows the appropriate empty/cold-start state (no error).
- Unknown `event_id` on any interaction → 404.
- Invalid dismiss reason → 422.
- Telemetry write failures inside the service must not corrupt the response: impressions are written in the same transaction as the read and committed once; if that fails, the request 500s (acceptable — it means the DB is broken).
- Frontend interaction failures are swallowed (except start-playing rollback).

## 10. Testing

**Backend (pytest):**
- `ml/heuristic` (pure, no mocks): ranking order for a crafted profile; each reason_code fires under its condition; exclusions drop hidden/abandoned/not_interested; completed + low-enjoyment sink; cold-start (empty `high_rated_genres`) still returns ranked candidates; determinism (stable tie-break).
- `ml/explanations` (pure): code list → sentence for representative combinations; always non-empty.
- `library_sync`: genres/themes persisted as `GameTag` of the right kind; re-sync replaces rather than duplicates.
- `recommender_service` (fake repos): builds correct `GameFeatures`/`UserProfile`; writes one impression per returned card; respects `limit`.
- `RecommendationEventRepository`: create/get/mark_* roundtrips.
- `recommendations` API: `GET /api/for-you` logs impressions and returns `event_id`s; click/dismiss/start-playing update the row; start-playing sets status; unknown id → 404; bad reason → 422.

**Frontend:**
- Vitest on any pure client helper (e.g. dismiss-reason labels). The backend owns the explanation sentence, so no client templating to test.
- `vite build` + manual walk-through + live smoke (load For You, dismiss a card with reason, start-playing a card → verify status flips on the Library page, verify a `recommendation_events` row exists).

**Conventions:** backend full red-green TDD; frontend pure-logic Vitest + build/manual (no component runner). ASCII UI strings (Windows mojibake). `ml/` package must import nothing from `app.db`, `app.api`, `app.services`, FastAPI, or SQLAlchemy — enforce with a test that imports `app.ml.*` and asserts those modules are absent from its transitive imports (a simple guard test).

## 11. File map (new / modified)

**Backend**
- Modify: `app/services/library_sync.py` (write genres/themes as tags); `app/db/repositories.py` (`replace_tags` / tag handling; new `RecommendationEventRepository`).
- Create: `app/ml/__init__.py`, `app/ml/types.py`, `app/ml/weights.py`, `app/ml/heuristic.py`, `app/ml/explanations.py`.
- Create: `app/services/recommender_service.py` (+ `CandidateSource`, `OwnedLibraryCandidateSource`).
- Create: `app/api/recommendations.py`; modify `app/main.py`.
- Tests: new `test_ml_heuristic.py`, `test_ml_explanations.py`, `test_ml_purity.py`, `test_recommender_service.py`, `test_recommendations_api.py`; extend `test_library_sync.py`, `test_repositories.py`.

**Frontend**
- Modify: `src/lib/api.ts` (For You types + functions); `src/components/AppShell.tsx` (nav link); `src/App.tsx` (route).
- Create: `src/pages/ForYouPage.tsx`, `src/components/ForYouCard.tsx`, and a small `src/lib/dismissReasons.ts` (+ Vitest).

## 12. Open questions

None outstanding. The candidate-set scope (owned-now with a buyable seam), telemetry depth (impression + click + dismiss + start-playing), the pure `ml/` boundary, and no-caching-in-v0 are all settled.
