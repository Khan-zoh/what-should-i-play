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
