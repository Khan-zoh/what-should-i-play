import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, apiPut, type LibraryItem } from "@/lib/api";
import GameCard from "@/components/GameCard";
import QuickRatePanel from "@/components/QuickRatePanel";
import { Button } from "@/components/ui/button";

type Sort = "name" | "hours" | "rating";

export default function LibraryPage() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("name");
  const [ratedOnly, setRatedOnly] = useState(false);
  const [active, setActive] = useState<LibraryItem | null>(null);
  // Game ids with an in-flight mutation; controls disable to avoid out-of-order
  // writes (single-user, but cheap correctness insurance).
  const [pending, setPending] = useState<ReadonlySet<number>>(new Set());

  const markPending = (gameId: number, on: boolean) =>
    setPending((prev) => {
      const next = new Set(prev);
      if (on) next.add(gameId);
      else next.delete(gameId);
      return next;
    });

  useEffect(() => {
    apiGet<LibraryItem[]>("/api/library")
      .then(setItems)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const patch = (gameId: number, fields: Partial<LibraryItem>) => {
    setItems((prev) =>
      prev.map((it) => (it.game_id === gameId ? { ...it, ...fields } : it)),
    );
    setActive((cur) =>
      cur && cur.game_id === gameId ? { ...cur, ...fields } : cur,
    );
  };

  const rate = async (item: LibraryItem, value: number | null) => {
    if (pending.has(item.game_id)) return;
    const prev = item.enjoyment;
    markPending(item.game_id, true);
    patch(item.game_id, { enjoyment: value }); // optimistic
    try {
      await apiPost(`/api/library/games/${item.game_id}/rating`, {
        enjoyment: value,
      });
    } catch {
      patch(item.game_id, { enjoyment: prev }); // rollback
    } finally {
      markPending(item.game_id, false);
    }
  };

  const setStatus = async (item: LibraryItem, status: string | null) => {
    if (pending.has(item.game_id)) return;
    const prev = item.status;
    markPending(item.game_id, true);
    patch(item.game_id, { status }); // optimistic
    try {
      await apiPut(`/api/library/games/${item.game_id}/status`, { status });
    } catch {
      patch(item.game_id, { status: prev }); // rollback
    } finally {
      markPending(item.game_id, false);
    }
  };

  const visible = useMemo(() => {
    const filtered = ratedOnly
      ? items.filter((i) => i.enjoyment !== null)
      : items;
    return [...filtered].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "hours") return b.hours_played - a.hours_played;
      return (b.enjoyment ?? 0) - (a.enjoyment ?? 0);
    });
  }, [items, sort, ratedOnly]);

  if (loading) return <p>Loading library...</p>;
  if (error) return <p className="text-red-600">Failed to load: {error}</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">
          Library ({items.length})
        </h1>
        <Button
          size="sm"
          variant={ratedOnly ? "default" : "outline"}
          onClick={() => setRatedOnly((v) => !v)}
        >
          Rated only
        </Button>
        {(["name", "hours", "rating"] as Sort[]).map((s) => (
          <Button
            key={s}
            size="sm"
            variant={sort === s ? "default" : "outline"}
            onClick={() => setSort(s)}
          >
            {s === "name" ? "A-Z" : s === "hours" ? "Most played" : "Top rated"}
          </Button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="text-muted-foreground">No games match this filter.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {visible.map((item) => (
            <GameCard
              key={item.game_id}
              item={item}
              onQuickRate={setActive}
            />
          ))}
        </div>
      )}

      <QuickRatePanel
        item={active}
        pending={active ? pending.has(active.game_id) : false}
        onOpenChange={(open) => !open && setActive(null)}
        onRate={rate}
        onStatus={setStatus}
      />
    </div>
  );
}
