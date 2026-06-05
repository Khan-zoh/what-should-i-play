import { useEffect, useState } from "react";
import { apiGet, apiPut, type Preferences } from "@/lib/api";
import { Button } from "@/components/ui/button";

const GENRES = [
  "RPG",
  "Shooter",
  "Strategy",
  "Roguelike",
  "Platformer",
  "Simulation",
  "Sports",
  "Puzzle",
  "Adventure",
  "Fighting",
];
const TYPES = ["singleplayer", "multiplayer", "co-op", "competitive"];
const SESSION_LENGTHS = ["any", "short", "medium", "long"];
const DIFFICULTIES = ["any", "easy", "medium", "hard"];

function toggle(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<Preferences>("/api/preferences").then(setPrefs);
  }, []);

  if (!prefs) return <p>Loading preferences...</p>;

  const save = async () => {
    await apiPut("/api/preferences", prefs);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const Chips = ({
    options,
    selected,
    onToggle,
  }: {
    options: string[];
    selected: string[];
    onToggle: (v: string) => void;
  }) => (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <Button
          key={o}
          size="sm"
          variant={selected.includes(o) ? "default" : "outline"}
          onClick={() => onToggle(o)}
        >
          {o}
        </Button>
      ))}
    </div>
  );

  return (
    <div className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-semibold">Preferences</h1>

      <section className="space-y-2">
        <h2 className="font-medium">Genres you like</h2>
        <Chips
          options={GENRES}
          selected={prefs.liked_genres}
          onToggle={(v) =>
            setPrefs({ ...prefs, liked_genres: toggle(prefs.liked_genres, v) })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Genres you dislike</h2>
        <Chips
          options={GENRES}
          selected={prefs.disliked_genres}
          onToggle={(v) =>
            setPrefs({
              ...prefs,
              disliked_genres: toggle(prefs.disliked_genres, v),
            })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Types you enjoy</h2>
        <Chips
          options={TYPES}
          selected={prefs.liked_types}
          onToggle={(v) =>
            setPrefs({ ...prefs, liked_types: toggle(prefs.liked_types, v) })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Preferred session length</h2>
        <div className="flex flex-wrap gap-2">
          {SESSION_LENGTHS.map((o) => (
            <Button
              key={o}
              size="sm"
              variant={prefs.session_length_pref === o ? "default" : "outline"}
              onClick={() => setPrefs({ ...prefs, session_length_pref: o })}
            >
              {o}
            </Button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Preferred difficulty</h2>
        <div className="flex flex-wrap gap-2">
          {DIFFICULTIES.map((o) => (
            <Button
              key={o}
              size="sm"
              variant={prefs.difficulty_pref === o ? "default" : "outline"}
              onClick={() => setPrefs({ ...prefs, difficulty_pref: o })}
            >
              {o}
            </Button>
          ))}
        </div>
      </section>

      <div className="flex items-center gap-3">
        <Button onClick={save}>Save preferences</Button>
        {saved && <span className="text-sm text-green-600">Saved</span>}
      </div>
    </div>
  );
}
