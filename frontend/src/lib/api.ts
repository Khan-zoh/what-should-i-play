const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: string;
}

async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${method} ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const apiPost = <T>(path: string, body?: unknown) =>
  apiSend<T>("POST", path, body);
export const apiPut = <T>(path: string, body?: unknown) =>
  apiSend<T>("PUT", path, body);

export interface LibraryItem {
  game_id: number;
  name: string;
  slug: string;
  steam_appid: number | null;
  igdb_id: number | null;
  hours_played: number;
  cover_url: string | null;
  critic_score: number | null;
  store_url: string | null;
  enjoyment: number | null;
  status: string | null;
}

export interface Preferences {
  liked_genres: string[];
  disliked_genres: string[];
  liked_types: string[];
  session_length_pref: string;
  difficulty_pref: string;
}

export interface OnboardingStatus {
  completed: boolean;
}

export interface SyncResult {
  run_id: number;
  status: "ok" | "partial" | "failed";
  counts: Record<string, number>;
  error: string | null;
  error_code: string | null;
}

export const getOnboarding = () => apiGet<OnboardingStatus>("/api/onboarding");
export const setOnboarding = (completed: boolean) =>
  apiPut<OnboardingStatus>("/api/onboarding", { completed });
export const syncSteam = (steamId?: string) =>
  apiPost<SyncResult>(
    "/api/library/sync/steam",
    steamId ? { steam_id: steamId } : {},
  );

export interface ForYouItem {
  event_id: number;
  game_id: number;
  name: string;
  slug: string;
  cover_url: string | null;
  genres: string[];
  critic_score: number | null;
  hours_played: number;
  status: string | null;
  reason_codes: string[];
  explanation: string;
  score: number;
  model_version: string;
}

export const getForYou = (limit = 20) =>
  apiGet<{ items: ForYouItem[] }>(`/api/for-you?limit=${limit}`);
export const postRecClick = (eventId: number) =>
  apiPost(`/api/recommendations/${eventId}/click`, {});
export const postRecDismiss = (eventId: number, reason: string) =>
  apiPost(`/api/recommendations/${eventId}/dismiss`, { reason });
export const postRecStartPlaying = (eventId: number) =>
  apiPost(`/api/recommendations/${eventId}/start-playing`, {});

export interface EmbedReport {
  model: string;
  attempted: number;
  embedded: number;
  skipped_existing: number;
  failed: { game_id: number; error: string }[];
}

export const postEmbeddingsRebuild = (force = false) =>
  apiPost<EmbedReport>(`/api/embeddings/rebuild${force ? "?force=true" : ""}`, {});
