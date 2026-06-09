import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getForYou,
  postRecClick,
  postRecDismiss,
  postRecStartPlaying,
  type ForYouItem,
} from "@/lib/api";
import ForYouCard from "@/components/ForYouCard";
import { Button } from "@/components/ui/button";

export default function ForYouPage() {
  const [items, setItems] = useState<ForYouItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ReadonlySet<number>>(new Set());
  const navigate = useNavigate();

  useEffect(() => {
    getForYou()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const mark = (id: number, on: boolean) =>
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const remove = (eventId: number) =>
    setItems((prev) => prev.filter((i) => i.event_id !== eventId));

  const onClick = (item: ForYouItem) => {
    postRecClick(item.event_id).catch(() => {}); // best-effort telemetry
  };

  const onStartPlaying = async (item: ForYouItem) => {
    if (busy.has(item.event_id)) return;
    mark(item.event_id, true);
    try {
      await postRecStartPlaying(item.event_id);
      remove(item.event_id);
    } catch {
      // leave the card in place on failure
    } finally {
      mark(item.event_id, false);
    }
  };

  const onDismiss = async (item: ForYouItem, reason: string) => {
    if (busy.has(item.event_id)) return;
    mark(item.event_id, true);
    remove(item.event_id); // optimistic
    try {
      await postRecDismiss(item.event_id, reason);
    } catch {
      // telemetry failure is non-fatal; card stays removed
    } finally {
      mark(item.event_id, false);
    }
  };

  if (loading) return <p>Loading recommendations...</p>;
  if (error) return <p className="text-red-600">Failed to load: {error}</p>;

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-md space-y-4 py-16 text-center">
        <h1 className="text-2xl font-semibold">Nothing to recommend yet</h1>
        <p className="text-muted-foreground">
          Import your Steam library and rate a few games to get picks.
        </p>
        <Button onClick={() => navigate("/onboarding")}>Import from Steam</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">For You</h1>
        <span className="text-xs text-muted-foreground">
          ranked by: {items[0]?.model_version}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <ForYouCard
            key={item.event_id}
            item={item}
            busy={busy.has(item.event_id)}
            onClick={onClick}
            onStartPlaying={onStartPlaying}
            onDismiss={onDismiss}
          />
        ))}
      </div>
    </div>
  );
}
