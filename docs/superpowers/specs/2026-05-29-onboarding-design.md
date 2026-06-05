# Sub-plan 2c — Onboarding, First-Run Detection & Steam-Failure UX (Design Spec)

**Date:** 2026-05-29
**Status:** Approved (pending spec review)
**Depends on:** Foundation, Sub-plan 2a (library import backend), Sub-plan 2b (library page + ratings + preferences UI).

---

## 1. Goal

Give a first-time user a guided path from an empty app to an imported, taste-annotated library, and handle Steam import failures with distinct, actionable guidance. This is also the **first UI surface that can trigger a Steam sync at all** — until now `POST /api/library/sync/steam` has only ever been called via curl.

A new user should be able to: open the app → be routed into onboarding → connect their Steam library (or skip) → set genre/type/length/difficulty preferences → land in the Library. A returning user skips onboarding entirely. Anyone can re-run onboarding on demand.

## 2. Scope

**In scope**
- A 3-step onboarding wizard at a standalone `/onboarding` route: **Welcome → Connect Steam → Preferences**.
- First-run detection via a persisted `onboarding_completed` flag, with a redirect guard.
- Machine-readable Steam sync error codes and a full failure taxonomy in the Connect step.
- A "Re-run setup" entry point on the Preferences page.
- A proper first-time empty state on the Library page.

**Out of scope (deferred)**
- True streaming / per-game import progress (the sync endpoint is a single synchronous POST; we show an indeterminate indicator).
- Manual game entry for Xbox / pirated titles (later sub-plan).
- Editing the Steam API key from the UI (it stays in `backend/.env`).
- A full Settings page (sub-plan 10).
- Multi-account / multi-user.
- Seed-ratings step (ratings are captured on the Library page from 2b).

## 3. Architecture overview

```
App
└─ OnboardingGuard            (fetches GET /api/onboarding once; spinner while loading)
   ├─ /onboarding             (standalone, full-screen, NO AppShell nav)
   │   └─ OnboardingWizard    (step state: welcome → connect → preferences → done)
   │        ├─ WelcomeStep
   │        ├─ ConnectStep    (Steam ID + import + failure taxonomy)
   │        └─ PreferencesStep (reuses shared PreferencesForm)
   └─ AppShell                (nav layout)
        ├─ /            LibraryPage      (+ new first-time empty state)
        └─ /preferences PreferencesPage  (+ "Re-run setup" button, reuses PreferencesForm)
```

Backend adds: machine-readable `error_code` on the sync outcome, a `SteamAuthError`, a public-empty-library success path, an `onboarding_completed` column on the `Preferences` singleton, and a thin `GET/PUT /api/onboarding` router.

## 4. Backend design

### 4.1 Steam client (`app/services/steam_client.py`)

- Add `SteamAuthError(SteamClientError)` for HTTP **401/403** (missing or invalid API key).
- **Public-but-empty library fix.** Currently any `response` payload without a `games` key raises `PrivateProfileError`. Refine:
  - If `games` is absent **and** `game_count == 0` is present → return `SteamLibraryResult(game_count=0, games=[])` (a valid empty library, not an error).
  - If `games` is absent **and** there is no `game_count` (truly `{"response": {}}`) → `PrivateProfileError` as today.
- **Narrow exception wrapping.** Wrap only `httpx.HTTPStatusError` and `httpx.RequestError` (transport/network/unexpected HTTP) into `SteamClientError`. Do **not** wrap `KeyError`/`ValueError` from JSON parsing — those indicate real bugs and should surface as 500 in dev.
- Status-code mapping stays: 429 → `SteamRateLimitError`; ≥500 → `InvalidSteamIdError`; 401/403 → `SteamAuthError`; other non-2xx → generic `SteamClientError`.

**Known limitation (documented, not fixed here):** `invalid_steamid` is best-effort — it keys off a 5xx response. A malformed-but-parseable Steam ID can instead return an empty response and surface as `private_profile`. Hardening Steam-ID validation is out of scope.

### 4.2 Sync orchestration (`app/services/library_sync.py`)

- `SyncOutcome` gains `error_code: str | None` (default `None`).
- On the failure path, map the caught exception type → code via a small isinstance ladder (most specific first):

  | Exception | `error_code` |
  |---|---|
  | `PrivateProfileError` | `private_profile` |
  | `SteamAuthError` | `steam_auth` |
  | `SteamRateLimitError` | `rate_limited` |
  | `InvalidSteamIdError` | `invalid_steamid` |
  | other `SteamClientError` (incl. wrapped network) | `steam_error` |

  (Order matters because the rate-limit/auth/invalid types all subclass `SteamClientError`.)
- Success outcomes (`ok`, `partial`) carry `error_code=None`. A **0-game success** is `status="ok"`, `counts={"added":0,"updated":0,"unmatched_igdb":0}` — not a failure.

### 4.3 Library API (`app/api/library.py`)

- `SyncOutcomeOut` gains `error_code: str | None`. No behavioral change to the request contract (`steam_id` still optional, falls back to `settings.steam_user_id`).

### 4.4 Onboarding flag

- **Model:** add `onboarding_completed: Mapped[bool]` (default `False`, not-null) to the `Preferences` model.
- **Migration:** one Alembic revision. **Must use `op.batch_alter_table`** for both `add_column` (upgrade) and `drop_column` (downgrade) so the SQLite round-trip in CI passes. Upgrade sets a server default of `False` so the existing singleton row is backfilled.
- **Repository:** extend `PreferencesRepository` with `get_onboarding_completed() -> bool` and `set_onboarding_completed(value: bool) -> None` (operating on the singleton via `get_or_create`). `PreferencesRepository.update()` continues to write **only** the five taste fields, so saving preferences never clobbers the flag.
- **Router:** new `app/api/onboarding.py`, registered in `main.py`, using the shared `get_db_session` from `app/api/deps.py`:
  - `GET /api/onboarding` → `{ "completed": bool }`
  - `PUT /api/onboarding` body `{ "completed": bool }` → sets the flag, returns the new state.

## 5. Frontend design

### 5.1 API client (`src/lib/api.ts`)

- Types: `OnboardingStatus { completed: boolean }`; `SyncResult { run_id: number; status: "ok"|"partial"|"failed"; counts: Record<string, number>; error: string|null; error_code: string|null }`.
- Functions: `getOnboarding()`, `setOnboarding(completed)`, `syncSteam(steamId?: string)` (POST, optional body).

### 5.2 Onboarding messages (`src/lib/onboardingMessages.ts`) — pure, unit-tested

A pure function `messageForErrorCode(code: string | null)` → `{ title, guidance, allowIdReentry: boolean }`:

| `error_code` | title | guidance | re-entry? |
|---|---|---|---|
| `private_profile` | "Your Steam profile is private" | How to set Steam → Edit Profile → Privacy → Game Details = Public, then Retry | no |
| `invalid_steamid` | "That Steam ID didn't work" | Re-enter your 17-digit Steam ID and try again | **yes** |
| `rate_limited` | "Steam is busy right now" | Rate-limited; wait a moment and Retry | no |
| `steam_auth` | "Server Steam API key problem" | The key in `backend/.env` is missing or invalid; fix it and Retry | no |
| `steam_error` / unknown | "Import failed" | Show the raw error; Retry | no |

Mirrors `ratings.ts`: pure module, no React/IO, covered by Vitest.

### 5.3 Routing & guard

- `main.tsx` / `App.tsx`: add a standalone `/onboarding` route **outside** `AppShell` (full-screen, no nav). Keep `/` and `/preferences` under `AppShell`.
- `OnboardingGuard` wraps the routed app:
  - On mount, `getOnboarding()`. While loading, render a centered spinner (**not** the app — prevents a library flash before redirect).
  - If `!completed` **and** `pathname !== "/onboarding"` → redirect to `/onboarding`.
  - `/onboarding` always renders regardless of the flag, so **re-run works** and there is **no redirect loop**.

### 5.4 Wizard (`src/pages/OnboardingWizard.tsx` + step components)

Local step state `"welcome" | "connect" | "preferences"`. A header shows step progress and a single **"Skip setup"** link that sets `completed=true` and navigates to `/` (the one true bail-out).

- **WelcomeStep** — one-line intro of what the app does + "Get started" → `connect`.
- **ConnectStep** (`src/components/onboarding/ConnectStep.tsx`):
  - Optional Steam ID text field, placeholder "Leave blank to use your server's configured ID".
  - "Import library" button → `syncSteam(id || undefined)`. Button **disabled while in-flight**; shows an indeterminate "Importing your library…" indicator.
  - On `status: "ok"`/`"partial"`: show success with counts (`added`/`updated`); for `partial` add an info line "N games couldn't be matched to rich metadata — they're still in your library"; for 0 games show "Connected — found 0 games". Primary button → `preferences`.
  - On `status: "failed"`: render the failure card from `messageForErrorCode(error_code)` with a **Retry** button; if `allowIdReentry`, focus the Steam ID field. A secondary **"Skip import"** button advances to `preferences` (taste still gets captured; library can be synced later).
- **PreferencesStep** (`src/components/onboarding/PreferencesStep.tsx`):
  - Renders the shared `PreferencesForm` (see 5.5), seeded from `GET /api/preferences`.
  - "Finish" → `PUT /api/preferences` (save) then `setOnboarding(true)` then navigate to `/`.

### 5.5 Shared `PreferencesForm` (DRY refactor)

Extract the genre/type/session-length/difficulty controls from the 2b `PreferencesPage` into a controlled `src/components/PreferencesForm.tsx` (`value: Preferences`, `onChange`). Both `PreferencesPage` and the onboarding `PreferencesStep` consume it. `PreferencesPage` keeps its own fetch/save/"Saved" affordance and gains a **"Re-run setup"** button → `navigate("/onboarding")`.

### 5.6 Library first-time empty state

`LibraryPage`: when `items.length === 0` (the whole library, independent of filters), render a dedicated empty state — "Your library is empty. Import your Steam games to get started." with an **"Import from Steam"** button → `/onboarding`. This is distinct from the existing "No games match this filter." message (which applies when filters exclude everything but the library is non-empty).

## 6. Data flow

1. App load → `OnboardingGuard` calls `GET /api/onboarding`.
2. `completed === false` → redirect to `/onboarding`.
3. Connect step → `POST /api/library/sync/steam` (optional `steam_id`). Success advances; failure shows taxonomy (Retry / Skip import).
4. Preferences step → `PUT /api/preferences`.
5. Finish → `PUT /api/onboarding {completed:true}` → navigate `/`.
6. Re-run later → "Re-run setup" (Preferences page) or "Import from Steam" (empty library) → `/onboarding`. The guard does not force-redirect away; finishing re-sets the flag idempotently.

Closing the tab mid-wizard leaves `completed=false`, so onboarding reappears next load — intended.

## 7. Error handling summary

- **Backend:** every Steam failure mode maps to a stable `error_code`; partial and 0-game results are successes; parse-level bugs intentionally remain uncaught (500).
- **Frontend:** `error_code` drives a deterministic message; unknown codes fall back to the `steam_error` card with the raw message; the Import button can't double-submit; "Skip import" and "Skip setup" both keep the user unblocked.

## 8. Testing strategy

**Backend (pytest + respx):**
- `steam_client`: 401→`SteamAuthError`, 403→`SteamAuthError`, 429→`SteamRateLimitError`, 5xx→`InvalidSteamIdError`, empty `{}`→`PrivateProfileError`, `{game_count:0}`→empty success, network error (respx `side_effect`)→`SteamClientError`, and that a JSON `KeyError` is **not** swallowed.
- `library_sync`: each exception type → expected `error_code`; 0-game success → `status="ok"`, `error_code=None`.
- `library` API: `SyncOutcomeOut` includes `error_code` (mock the service).
- `onboarding` API: GET default `false`; PUT toggles and persists; `PUT /api/preferences` does **not** reset `onboarding_completed`.
- Alembic upgrade→downgrade→upgrade round-trip (the CI job already runs this).

**Frontend:**
- Vitest: `messageForErrorCode` for every code + unknown fallback.
- `vite build` (zero TS errors) + manual flow check: first-run redirect, import success/partial/0-games, a failure path (use a bogus Steam ID to trigger a real error), preferences save, finish → library, re-run from both entry points, empty-state CTA.

**Conventions carried over:** backend is full red-green TDD; frontend uses scoped Vitest for pure logic + build/manual for components (no component test runner — accepted trade-off). UTF-8 caution on the Windows box: prefer ASCII in UI strings where a glyph isn't essential.

## 9. File map (new / modified)

**Backend**
- Modify: `app/services/steam_client.py` (SteamAuthError, empty-library success, narrow wrapping)
- Modify: `app/services/library_sync.py` (`error_code` + mapping)
- Modify: `app/api/library.py` (`SyncOutcomeOut.error_code`)
- Modify: `app/db/models.py` (`Preferences.onboarding_completed`)
- Modify: `app/db/repositories.py` (`PreferencesRepository` get/set onboarding)
- Create: `app/api/onboarding.py`; Modify: `app/main.py` (register router)
- Create: `alembic/versions/<rev>_add_onboarding_completed.py` (batch op)
- Tests: extend `test_steam_client.py`, `test_library_sync.py`, `test_library_api.py`; new `test_onboarding_api.py`; extend `test_repositories.py`

**Frontend**
- Modify: `src/lib/api.ts` (onboarding + sync types/functions)
- Create: `src/lib/onboardingMessages.ts` + `src/lib/onboardingMessages.test.ts`
- Create: `src/components/OnboardingGuard.tsx`
- Create: `src/pages/OnboardingWizard.tsx`
- Create: `src/components/onboarding/WelcomeStep.tsx`, `ConnectStep.tsx`, `PreferencesStep.tsx`
- Create: `src/components/PreferencesForm.tsx` (extracted)
- Modify: `src/pages/PreferencesPage.tsx` (use form + Re-run button), `src/pages/LibraryPage.tsx` (empty state), `src/App.tsx` / `src/main.tsx` (routes + guard)

## 10. Open questions

None outstanding — the nine review refinements (exception wrapping, empty-library success, invalid_steamid limitation, preferences-save flag safety, batch migration, guard anti-flicker/loop, skip semantics, library empty state, import double-submit) are folded into the sections above.
