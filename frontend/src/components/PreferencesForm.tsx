import type { Preferences } from "@/lib/api";
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

function Chips({
  options,
  selected,
  onToggle,
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
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
}

interface Props {
  value: Preferences;
  onChange: (next: Preferences) => void;
}

export default function PreferencesForm({ value, onChange }: Props) {
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h2 className="font-medium">Genres you like</h2>
        <Chips
          options={GENRES}
          selected={value.liked_genres}
          onToggle={(v) =>
            onChange({ ...value, liked_genres: toggle(value.liked_genres, v) })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Genres you dislike</h2>
        <Chips
          options={GENRES}
          selected={value.disliked_genres}
          onToggle={(v) =>
            onChange({
              ...value,
              disliked_genres: toggle(value.disliked_genres, v),
            })
          }
        />
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Types you enjoy</h2>
        <Chips
          options={TYPES}
          selected={value.liked_types}
          onToggle={(v) =>
            onChange({ ...value, liked_types: toggle(value.liked_types, v) })
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
              variant={value.session_length_pref === o ? "default" : "outline"}
              onClick={() => onChange({ ...value, session_length_pref: o })}
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
              variant={value.difficulty_pref === o ? "default" : "outline"}
              onClick={() => onChange({ ...value, difficulty_pref: o })}
            >
              {o}
            </Button>
          ))}
        </div>
      </section>
    </div>
  );
}
