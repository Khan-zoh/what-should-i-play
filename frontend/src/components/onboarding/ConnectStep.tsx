import { useState } from "react";
import { postEmbeddingsRebuild, syncSteam, type SyncResult } from "@/lib/api";
import { messageForErrorCode } from "@/lib/onboardingMessages";
import { Button } from "@/components/ui/button";

export default function ConnectStep({ onNext }: { onNext: () => void }) {
  const [steamId, setSteamId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SyncResult | null>(null);

  const runImport = async () => {
    if (busy) return;
    setBusy(true);
    setResult(null); // clear any prior card so a retry shows a clean in-progress state
    try {
      const r = await syncSteam(steamId.trim() || undefined);
      setResult(r);
      if (r.status === "ok" || r.status === "partial") {
        // Fire-and-forget: warm content embeddings for the freshly imported
        // library. Failure (e.g. [ml] extra not installed) is non-fatal; the
        // recommender falls back to genre similarity until a rebuild succeeds.
        postEmbeddingsRebuild().catch(() => {});
      }
    } catch {
      setResult({
        run_id: 0,
        status: "failed",
        counts: {},
        error: "Network error",
        error_code: "steam_error",
      });
    } finally {
      setBusy(false);
    }
  };

  const succeeded = result?.status === "ok" || result?.status === "partial";
  const added = (result?.counts.added ?? 0) + (result?.counts.updated ?? 0);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Connect your Steam library</h1>
        <p className="text-muted-foreground">
          Enter your 17-digit Steam ID, or leave it blank to use the ID from
          your server config.
        </p>
      </div>

      <input
        aria-label="Steam ID"
        className="w-full rounded-md border border-border bg-background px-3 py-2"
        placeholder="Leave blank to use server-configured ID"
        value={steamId}
        onChange={(e) => setSteamId(e.target.value)}
      />

      <div className="flex items-center gap-3">
        <Button onClick={runImport} disabled={busy}>
          {busy ? "Importing your library..." : "Import library"}
        </Button>
      </div>

      {succeeded && (
        <div className="space-y-3 rounded-md border border-green-600/40 p-4">
          <p className="text-green-700">
            {added === 0
              ? "Connected - found 0 games in this library."
              : `Imported ${added} games.`}
          </p>
          {result?.status === "partial" && (
            <p className="text-sm text-muted-foreground">
              {result.counts.unmatched_igdb} game(s) couldn't be matched to rich
              metadata - they're still in your library.
            </p>
          )}
          <Button onClick={onNext}>Next</Button>
        </div>
      )}

      {result?.status === "failed" && (
        <FailureCard
          code={result.error_code}
          rawError={result.error}
          onRetry={runImport}
          onSkip={onNext}
        />
      )}
    </div>
  );
}

function FailureCard({
  code,
  rawError,
  onRetry,
  onSkip,
}: {
  code: string | null;
  rawError: string | null;
  onRetry: () => void;
  onSkip: () => void;
}) {
  const msg = messageForErrorCode(code);
  return (
    <div className="space-y-3 rounded-md border border-red-600/40 p-4">
      <p className="font-medium text-red-700">{msg.title}</p>
      <p className="text-sm text-muted-foreground">{msg.guidance}</p>
      {code === "steam_error" && rawError && (
        <p className="text-xs text-muted-foreground">Details: {rawError}</p>
      )}
      <div className="flex gap-3">
        <Button onClick={onRetry}>Retry</Button>
        <Button variant="outline" onClick={onSkip}>
          Skip import
        </Button>
      </div>
    </div>
  );
}
