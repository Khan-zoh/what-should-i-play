# What Should I Play? — Design Spec

**Date:** 2026-05-15
**Status:** Draft for review
**Author:** Zohair (with brainstorming assistance)

---

## 1. Overview & Goals

**What we're building:** A local, single-user web application that recommends what to play tonight from games the user already owns, and recommends new games to buy when nothing in the existing library fits. Powered by a hybrid ranking pipeline (content-based embeddings + heuristic priors + an optional supervised reranker), with grounded LLM-rendered explanations and an offline evaluation harness.

**Core jobs the system does:**

1. **Knows the library** — auto-imports from Steam (Web API) and accepts manual entries for anything else (Xbox, GOG, Epic, pirated).
2. **Captures taste** — genre/type preferences, per-game enjoyment ratings, structured status (backlog, playing, completed, etc.), and freeform notes.
3. **Recommends new games to buy** — content-based candidate retrieval over an IGDB-sourced catalog, scored by a hybrid ranking pipeline.
4. **"What should I play tonight?"** — a 5-question structured mood quiz (with a schema-constrained freeform fallback) that returns a ranked list, owned games first, buy candidates collapsed below.
5. **Shows reviews and store links** — each result card surfaces Steam review score + count, IGDB critic score, price, a "View on Steam" / store-search button, and a grounded explanation.

**Resume framing (single line):** A hybrid game-recommendation pipeline using sentence-transformer embeddings for content retrieval, a regularized supervised reranker for per-user personalization, k-means library clustering for mood mapping with medoid exemplars, and a reproducible offline-eval harness comparing learned models against four baselines on a temporal holdout, instrumented with full impression/click/dismiss telemetry.

**Out of scope for v1 (explicit):**

- Multi-user accounts, authentication, public hosting
- Automatic import from Epic / GOG / Xbox (manual entry only)
- Social features, sharing, friend recommendations
- Native mobile app (the web UI is responsive but not installable)
- Aggregated review sources beyond Steam + IGDB (OpenCritic, Metacritic — defer to v2)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (React + Vite + TypeScript + Tailwind + shadcn/ui) │
│  - Onboarding wizard  - Library page    - Rate-a-game flow  │
│  - Mood quiz          - For You page    - Settings          │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / JSON
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI backend (Python 3.11+)                              │
│                                                              │
│   api/         routers: library, ratings, recommend, quiz   │
│   services/    steam_client, igdb_client, llm_client,       │
│                recommender_service                          │
│   ml/          embeddings, rating_model, clustering, eval   │
│                features, scoring  (PURE: no FastAPI/DB)     │
│   db/          SQLAlchemy models, Alembic, repositories     │
│   jobs/        background tasks (embedding refresh, retrain)│
└──────────┬───────────────────┬──────────────┬───────────────┘
           │                   │              │
       ┌───▼────┐         ┌────▼────┐    ┌────▼────────┐
       │ SQLite │         │  IGDB   │    │ Steam Web   │
       │  + FTS │         │   API   │    │     API     │
       └────────┘         └─────────┘    └─────────────┘
                                ┌────────────────────────┐
                                │  Anthropic API (LLM)   │
                                │  - mood-quiz extraction│
                                │  - explanation rewrite │
                                └────────────────────────┘
```

**Key decisions:**

- **Single FastAPI process.** `ml/` is a package, not a separate service. One `uvicorn` to run.
- **SQLite, not Postgres.** Single user, local. SQLite's FTS5 powers the manual-add search.
- **Embeddings stored as BLOBs in their own table** (`game_embeddings`), keyed by `(game_id, model_name)`, so swapping embedding models doesn't require a migration.
- **Background jobs via FastAPI `BackgroundTasks`** for v1. The design notes this as a known limitation that can graduate to APScheduler/Celery without architectural changes.
- **LLM calls** are cached by prompt hash in `llm_cache`; the product fully functions if the LLM is unavailable.
- **Secrets** (Steam API key, IGDB client ID/secret, Anthropic key) in `.env`; Anthropic key may be stored in OS keychain when available.

**Boundary discipline (resume-critical):**

The `ml/` package **takes plain dataclasses in and returns plain dataclasses out**. It imports neither SQLAlchemy nor FastAPI. The layering is:

- `ml/` — pure: models, feature schemas, scoring functions, eval primitives
- `services/recommender_service.py` — orchestration: loads from repositories, hands to `ml/`, writes results back
- `db/repositories.py` — all persistence
- `jobs/` — sync, train, embed workflows

This makes lifting `ml/` into a standalone Streamlit demo, a Kaggle notebook, or a separate microservice a clean operation rather than a refactor.

---

## 3. Data Model

SQLite with SQLAlchemy ORM and Alembic migrations.

### 3.1 Catalog

**`games`** — canonical catalog (union of imported library + IGDB candidates)
- `id` (PK), `igdb_id` (unique), `steam_appid` (nullable, unique when present)
- `name`, `slug`, `release_year`, `summary`
- `cover_url`, `store_url`
- `critic_score` (IGDB aggregate, nullable), `steam_review_score` (nullable), `steam_review_count`
- `price_usd` (nullable, refreshed periodically)
- `created_at`, `updated_at`

**`game_embeddings`** — versioned, per-model embeddings
- `id` (PK), `game_id` (FK)
- `model_name` (e.g. `all-MiniLM-L6-v2`), `dim` (e.g. 384)
- `embedding` (BLOB, float32), `created_at`
- `unique(game_id, model_name)`

**`game_tags`** — tags, genres, themes
- `game_id` (FK), `tag` (text), `kind` (`genre` | `theme` | `mechanic` | `mood`)
- Indexed on `(tag, kind)`

### 3.2 User data

**`library_entries`** — games the user has
- `id` (PK), `game_id` (FK, unique)
- `source` (`steam` | `manual`), `external_id` (Steam appid if applicable, else null)
- `hours_played` (float, auto from Steam, editable)
- `acquired_at` (nullable)

**`user_game_state`** — intent / status, separate from rating
- `game_id` (PK, FK)
- `status` (`backlog` | `installed` | `currently_playing` | `completed` | `abandoned` | `wishlisted` | `hidden` | `not_interested` | `want_to_replay` | `multiplayer_only` | `tried_and_refunded`)
- `updated_at`

**`ratings`** — explicit enjoyment
- `id` (PK), `game_id` (FK, unique)
- `enjoyment` (int 1–5, nullable; UI presents as Loved / Liked / Meh / Disliked / Hated, mapped to 5 / 4 / 3 / 2 / 1. "Haven't played" = no `ratings` row at all.)
- `finished` (bool, nullable)
- `notes` (text, nullable, short freeform)
- `rated_at`

**`play_sessions`** — finer-grained playtime
- `id` (PK), `game_id` (FK)
- `started_at`, `ended_at`, `duration_minutes`
- `source` (`steam` | `manual`)

**`preferences`** — singleton (id = 1)
- `liked_genres` (JSON array), `disliked_genres` (JSON array)
- `liked_types` (JSON: fps, mmo, rpg, roguelike, strategy, sim, puzzle, platformer, horror, co-op, etc.)
- `session_length_pref` (`short` | `medium` | `long` | `any`)
- `difficulty_pref` (`chill` | `balanced` | `hard` | `any`)
- `updated_at`

### 3.3 Telemetry & ML

**`quiz_sessions`** — each mood-quiz run
- `id` (PK), `mode` (`structured` | `freeform`)
- `answers` (JSON), `freeform_text` (nullable), `extracted_fields` (JSON; freeform's parsed JSON)
- `results` (JSON: ordered list of `{game_id, score, reason_codes, llm_blurb}`)
- `created_at`

**`recommendation_events`** — full impression/interaction telemetry
- `id` (PK), `game_id` (FK)
- `surface` (`quiz_result` | `for_you` | `library_browse`)
- `rank` (int), `score` (float), `reason_codes` (JSON)
- `model_version` (string), `feature_hash` (string), `filters_applied` (JSON)
- `cache_hit` (bool), `abstention_path` (`heuristic` | `ridge` | `lgbm`)
- `cluster_label` (nullable, mood surface), `explanation_variant` (`templated` | `llm`)
- `shown_at`, `clicked_at`, `dismissed_at`, `accepted_at`, `started_playing_at`
- `dismiss_reason` (nullable: `too_long` | `wrong_genre` | `too_expensive` | `wrong_platform` | `already_played_elsewhere` | `not_interested`)

**`model_runs`** — reproducible training/eval log
- `id` (PK), `model_type` (`ridge_reranker` | `lgbm_reranker` | `baseline_popularity` | `baseline_tag_overlap` | `baseline_centroid` | `baseline_hybrid_heuristic`)
- `trained_at`, `n_training_samples`
- `feature_version` (string), `embedding_model` (string)
- `split_strategy` (`temporal` | `leave_k_out`), `split_config` (JSON)
- `metrics` (JSON: rmse, precision_at_5, precision_at_10, ndcg_at_10, mrr, candidate_recall_at_100, coverage, novelty)
- `artifact_path` (filesystem path to pickled model)

**`data_sync_runs`** — import/sync log
- `id` (PK), `source` (`steam` | `igdb`)
- `status` (`ok` | `partial` | `failed`)
- `started_at`, `finished_at`, `counts` (JSON: added/updated/skipped), `error` (nullable)

**`llm_cache`** — prompt-hash → response cache
- `prompt_hash` (PK), `response_json`, `created_at`

### 3.4 Indices and search

- `library_entries.game_id`, `ratings.game_id`, `recommendation_events(game_id, shown_at)`
- `games.steam_appid`, `games.igdb_id`
- `game_embeddings(model_name)` for active-model filtering
- FTS5 virtual table over `games(name, summary)` for the manual-add search box

---

## 4. ML & Recommendation Pipeline

**Headline framing:** *Hybrid ranking pipeline with content retrieval, heuristic priors, and a lightweight personal reranker (when enough labels exist), evaluated against four baselines on a temporal holdout with full reproducibility.*

### 4.1 Pipeline overview

```
Candidate generation
  ├── Owned games (library_entries)
  └── Buy candidates (IGDB pool, basic constraint filter)

Scoring layers (weighted sum after per-layer calibration)
  ├── Content similarity     (cosine vs liked-game centroid)
  ├── Tag/genre overlap      (Jaccard, rule baseline)
  ├── Preference match       (liked/disliked genres + types)
  ├── Quality prior          (critic + Steam review, globally normalized)
  ├── Mood-cluster fit       (cosine to active cluster medoids)
  └── Personal reranker      (Ridge ≥ 30 ratings, LightGBM ≥ 100, with abstention)

Constraints / business rules
  ├── Exclude hidden, abandoned, not_interested
  ├── Owned-first ordering on mood surface
  ├── Session-length filter
  └── Price filter on "buy" surface

Explanation
  ├── Deterministic reason_codes (always)
  └── LLM-rewritten sentence (optional; templated fallback)
```

### 4.2 Cold-start path

Below 30 rated games: personal reranker disabled. Ranking uses content similarity (vs games rated 4–5 during onboarding + any seed ratings), preference match, and quality prior. The UI surfaces: *"Recommendations will get more personal as you rate more games."*

### 4.3 Feature calibration (before weighted sum)

- **Content cosine** → percentile rank within candidate set
- **Critic / review prior** → globally normalized to [0, 1]
- **Tag overlap** → Jaccard, not raw count
- **Price / session length** → hard filters (constraints), not soft weights
- **Cluster fit** → cosine to weighted mixture of active cluster medoids

### 4.4 Personal reranker

- **Phase 1 (N ≥ 30 ratings):** Ridge regression. Features = liked-centroid cosine, tag-Jaccard, genre/type one-hots, critic prior, price, release-year decay.
- **Phase 2 (N ≥ 100 ratings):** LightGBM with strict regularization (small `num_leaves`, monotonic constraints on `critic_score` and `tag_overlap`).
- **Label:** explicit `enjoyment` rating (1–5). Dismiss / accept events are logged as diagnostics, **not used as training labels in v1.**
- **Abstention rule:** if Phase-2 LightGBM does not beat Phase-1 Ridge by a configured margin on temporal holdout, the pipeline falls back to Ridge. If Ridge does not beat the hybrid-heuristic baseline, it falls back to the heuristic. Models are allowed to lose.

### 4.5 Embeddings

- Model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, CPU, free, local).
- Input text: `game.name + " — " + game.summary + " | tags: " + join(tags)`.
- Stored in `game_embeddings` keyed by `(game_id, model_name)`. Model swap = embed under a new key, switch active model name in config.

### 4.6 Mood-cluster mapping

- Cluster the **full library subset** (not just rated games) using k-means over embeddings.
- K chosen by elbow + silhouette, **capped at 5** so clusters stay human-nameable.
- Each cluster labeled from top tags and **medoid exemplar games** (e.g. *Cozy Puzzlers*, *Story RPGs*, *Twitchy Action*).
- If cluster silhouette is below a configured threshold, fall back to **predefined mood archetypes** (rule-based assignment of games to fixed archetypes).
- Structured quiz answers map deterministically to cluster weights via a lookup table — no learning at this layer.
- Framing in the design and the UI: *"an interpretable grouping aid, not a learned personalization model."*

### 4.7 Evaluation harness

**Splits**
- Primary: **temporal** — hold out the most recent 20% of ratings
- Secondary: leave-k-out

**Leakage controls**
- All features for held-out games computed using only data available *before* the holdout timestamp
- Liked-game centroid recomputed per fold
- Preferences snapshotted at the cutoff (or recomputed from pre-cutoff ratings)

**Candidate-generation eval (separate from ranking)**
- `candidate_recall_at_100` — fraction of held-out positives that appear in the top-100 candidate set. Ranking metrics are misleading if positives never enter candidates.

**Ranking baselines (all logged, all comparable)**
1. Popularity (Steam review count × score)
2. Tag-overlap (Jaccard)
3. Embedding-centroid (mean of liked-game embeddings, cosine over catalog)
4. Hybrid-heuristic (handcrafted weighted sum, no learning)

**Models evaluated:** Ridge reranker, LightGBM reranker.

**Metrics:** RMSE on rating prediction; precision@5, precision@10, NDCG@10, MRR on ranking; coverage and novelty as diagnostics; `candidate_recall_at_100` for retrieval quality.

**Output:** `notebooks/eval_report.ipynb` reads from `model_runs` and renders a comparison table + plots. Fold variance and confidence intervals are reported.

**Honesty caveat (baked into the eval section and any resume copy):**

> At this data scale (≈ 50–200 personal ratings), metrics are directional, not conclusive. The eval harness exists to prevent self-deception: compare against simple baselines, use temporal holdout, log reproducible runs, and allow learned models to lose. Fold variance is reported; statistically strong wins are not claimed.

### 4.8 Weight tuning

Hand-set weights initially, based on product intent and normalized feature scales. Tune only **three grouped weights** (`personal_match`, `content_similarity`, `quality_availability`) via coarse coordinate search on temporal validation. Require margin-over-baseline to accept changes. Report fold variance; if results are unstable across folds, keep defaults.

Honest internal/external framing: *"weights are config-calibrated, lightly validated, intentionally conservative because per-user data is small."*

### 4.9 Grounded explanations

Every recommendation produces a list of deterministic `reason_codes` first:

- `MATCHES_LIKED_GENRE:<genre>`
- `SIMILAR_TO_HIGH_RATED:<slug>`
- `MOOD_CLUSTER:<label>`
- `SHORT_SESSION_FRIENDLY`
- `HIGH_CRITIC_SCORE`
- `OWNED_AND_UNPLAYED`
- `BACKLOG_PRIORITY`
- `FITS_PRICE_CAP`

The LLM's only job is to **rewrite the code list into one natural sentence**. If Anthropic is unavailable or unconfigured, a templated string is used. The product is fully functional without the LLM. The "Why?" tooltip exposes the raw codes (and is the dev-debug surface).

### 4.10 Boundary discipline (restated)

- `ml/` takes `GameFeatures`, `UserProfile`, `RatedExample` in; returns `ScoredCandidate`, `ModelArtifact`, `EvalReport` out.
- No SQLAlchemy, no FastAPI, no I/O of any kind inside `ml/`.
- `services/recommender_service.py` owns orchestration.
- `db/repositories.py` owns persistence.
- `jobs/` owns workflow scheduling.

---

## 5. Core User Flows

### 5.1 First-run onboarding (~3 minutes)

1. **Welcome + Steam connect.** Optional Steam ID input. Background job fetches owned games + playtime via Steam Web API.
   - **Failure states explicitly handled:** private profile (clear copy + manual fallback), invalid ID (validation message), rate-limited (429 with retry-after), partial fetch (some appids missing metadata — flagged for later enrichment), "still importing" state (live progress).
2. **Preferences.** Multi-select chips: liked genres, disliked genres, liked types (FPS / RPG / MMO / roguelike / strategy / sim / puzzle / platformer / horror / co-op). Selectors for session-length preference and difficulty preference.
3. **Seed ratings (optional but encouraged).** Top 10 most-played games from import + a search box for manual additions.
   - Rating uses **Loved / Liked / Meh / Disliked / Hated** (mapped to 5 / 4 / 3 / 2 / 1 internally). "Haven't played" means leaving the game unrated — represented as the absence of a `ratings` row.
   - **"Played a lot but didn't like"** is a first-class option, so the centroid isn't poisoned by Steam's hours-played proxy.
   - Prompt copy: *"How much did **you personally enjoy** playing this?"* — not "rate this game."
4. **Done.** Land on the home page.

Any step is skippable; skipping seed ratings activates the cold-start path with a persistent "rate some games to personalize" prompt on the home page.

### 5.2 Library page

- Grid of cards: cover art, name, hours played, enjoyment label, status badge.
- Filters: status, source (Steam / manual), unrated only.
- Sorts: hours, rating, recently added, recently played.
- **Quick-rate side panel** (opens on card click): status dropdown, Loved/Liked/Meh/Disliked, finished checkbox, 1-line note.
- **Optimistic UI with rollback:** if the write fails, the card reverts and a toast surfaces the error. Labels never silently diverge from server state.
- **"+ Add game"** button → FTS5 search over local `games`; if no match, falls through to a live IGDB query that inserts the game on selection.

### 5.3 "For You" page (buy recommendations)

- Header: *"Based on your library and ratings."* Below it, an abstention-path indicator in small dev-mode-only text (heuristic / Ridge / LightGBM).
- ~20 result cards, each showing: cover, name, genre tags, Steam review score + count, IGDB critic score, price, **"View on Steam"** button (or generic store-search link), and the LLM-rendered explanation sentence.
- **"Why?"** tooltip on each card exposes the raw `reason_codes`.
- **Per-card controls:** More like this / Less like this / Dismiss-with-reason.
  - Dismiss reasons (structured): `too_long`, `wrong_genre`, `too_expensive`, `wrong_platform`, `already_played_elsewhere`, `not_interested`.
- Sidebar filters: price cap, exclude owned, genre includes/excludes, "show only games under 20 hours."
- **Cache behavior:** results cached for up to 24h; cache invalidated immediately on any rating change, preference edit, dismiss, or library addition.

### 5.4 Mood quiz — structured mode

- **Quick mode (default):** all 5 questions on a single screen with chip-style selectors.
  1. Energy: Low / Medium / High
  2. Brainpower: Off / Some / Sharp
  3. Session length: < 30 min / 30–90 min / 90+ min
  4. Solo or social: Solo / Co-op / Competitive
  5. Mood: Cozy / Story / Adventure / Tense / Competitive / Creative
- **Step mode:** same 5 questions one-per-screen for accessibility / first-time use.
- **Result-mode toggle** (above results): Surprise me / Continue something (filters to `currently_playing` + `backlog`) / Finish backlog (≥ 50% completed) / New only (excludes owned).
- Result header: *"Tonight you're in the mood for **\<cluster label\>**."*
- Result list: **owned games first**, divider, then collapsible *"Show new games to buy"* section with buy candidates.
- Each card identical to 5.3, with `reason_codes` extended by `MOOD_CLUSTER:<label>` and matched session/energy filters.
- **Rating affordances inline** on every result card.
- *"Not quite right?"* button switches to freeform mode, prefilled with the structured answers as context.

### 5.5 Mood quiz — freeform mode

- Single textarea: *"Tell me how you're feeling or what you want to play."*
- Submit → Anthropic API call with a **schema-constrained JSON output**:
  - All fields enum-constrained: `energy ∈ {low, medium, high, unknown}`, etc.
  - `unknown` is an explicit allowed value.
- **Interpretation confirmation step (always shown before results):**
  > *"I read this as low energy, short session, solo, cozy mood. Want to adjust before I recommend?"*
  - User can edit any extracted field via chips before continuing.
- If most fields come back `unknown`, the UI falls back to the structured quiz with one clarifying question instead of guessing.
- **Critical:** the LLM never picks games directly. It only translates language into the structured quiz inputs that feed the deterministic pipeline.

### 5.6 Settings

- **Steam sync:** last-sync timestamp + result count, force-sync button.
- **Model training:** "Last trained X minutes/hours ago" status; auto-triggers after N new ratings; force-retrain button.
- **Library clustering:** auto-runs after N new ratings or 10% library growth; force-recluster button; current cluster names listed.
- **Preferences editor:** same UI as onboarding step 2.
- **Anthropic API key:** masked input, "Test connection" button, "Delete key" wipes from disk. Stored in OS keychain when available, otherwise `.env`.
- **Export data:** download SQLite + JSON dump. Useful for demo seeding and portability.
- **Reset all data:** explicit confirmation, irreversible.

---

## 6. Logging & Eval Surfaces

Every recommendation impression writes a `recommendation_events` row with the full feature context (see 3.3). Subsequent click / dismiss / accept / started-playing actions update the row.

Mood-quiz results log whether a suggested game was **subsequently launched, accepted, or rated** — the only honest way to evaluate mood-cluster quality at small data scale.

Dismiss events carry a structured `dismiss_reason`. These are the negative signals that matter most when explicit positive labels are sparse.

The eval notebook reads from `recommendation_events` + `model_runs` and produces:

- Per-model precision / NDCG / MRR with fold variance
- Candidate-recall@100 per model
- Baseline comparison table
- Abstention-path distribution over time (how often Ridge wins vs LightGBM vs heuristic)
- Dismiss-reason breakdown by surface (where are recs going wrong, and why)

---

## 7. Privacy, Accessibility, Safety

**Privacy**

- Local-first. The application database lives on the user's machine; no remote backend in v1.
- The only data that leaves the device is:
  - Outbound calls to IGDB and Steam Web API for catalog/library data
  - The freeform mood text + extracted JSON sent to Anthropic (only when the freeform quiz is used and an API key is configured)
- Steam ID, Anthropic key, and exported data are stored locally only.
- Privacy copy surfaced during onboarding and at every settings entry that touches an external API.

**Accessibility**

- Keyboard-navigable rating and dismiss actions.
- Screen-reader labels on all status badges and reason-code tooltips.
- Status indicators use **icon + color**, never color alone.
- Step mode of the mood quiz is the accessible alternative to quick mode.

**LLM safety**

- All LLM calls use schema-constrained JSON output (enum-restricted fields) — kills prompt-injection meaningfully and prevents silent format drift.
- The LLM never selects games. It only rewrites grounded `reason_codes` into a sentence, or translates freeform mood text into structured quiz inputs.
- Templated fallback is always available; the product works fully without Anthropic.
- No PII is sent in prompts.

---

## 8. Demo Strategy (Future, Designed-In)

The architecture supports three demo paths without v1 rework:

1. **README + video walkthrough + screenshots.** Always works, zero hosting cost.
2. **Sandbox demo (v2).** A `DEMO_MODE` flag enables a pre-seeded curated library + session-scoped temp profile (wipes after 1h). Disables Steam import, caps LLM calls per session. Hosted on Fly.io / Render / a $5 VPS. Possible because of the `DEMO_MODE` seam and the `ml/` package's purity.
3. **Detached ML-only Streamlit demo (v2).** The same `ml/` package, loaded with a public Steam reviews dataset (Kaggle), running the recommender on a visitor-selected seed-game set. Possible because `ml/` has no FastAPI or DB dependencies.

The only v1 design impact: `ml/` must remain importable standalone, and a `DEMO_MODE` config flag should be reserved in the settings module.

---

## 9. Tech Stack Summary

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui | Modern, accessible, looks polished out of the box; resume-friendly |
| Backend | FastAPI (Python 3.11+) | Python plays to data-eng/ML background; FastAPI gives async, typed routes, OpenAPI |
| DB | SQLite + Alembic | Single-user local; FTS5 covers search; zero ops |
| ORM | SQLAlchemy | Type-safe, migration-friendly |
| ML | sentence-transformers, scikit-learn (Ridge, k-means), LightGBM, numpy | CPU-only, free, well-known, defensible |
| LLM | Anthropic API (Claude) | Schema-constrained JSON outputs |
| Background | FastAPI BackgroundTasks (v1) | Adequate for single-user; graduates to APScheduler/Celery later |
| External | Steam Web API, IGDB API | Free with sign-up; cover library + catalog |

---

## 10. Out of Scope / Future Work

- Multi-user accounts and authentication
- Epic / GOG / Xbox automatic library import
- Aggregated review sources (OpenCritic, Metacritic)
- Friend-graph or social recommendations
- Native mobile app
- A/B testing harness for explanation variants
- Real-time playtime tracking (beyond Steam delta snapshots)
- Active learning (model-suggested games to rate to fill information gaps)
- Sandbox demo mode and detached ML Streamlit demo (designed-in but built v2)

---

## 11. Open Questions

- Concrete onboarding copy for cold-start prompts and Steam-failure states (deferred to implementation plan).
- Exact thresholds for retrain triggers (N new ratings) and recluster triggers (library-growth %).
- Initial weight values for the scoring layers — to be hand-set during implementation and tuned via the eval harness.
- Whether to include OpenCritic as a deferred-v2 integration point in the data model now or add it later.
