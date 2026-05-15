import { useEffect, useState } from "react";
import { apiGet, type HealthResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";

type State =
  | { kind: "loading" }
  | { kind: "ok"; status: string }
  | { kind: "error"; message: string };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const check = () => {
    setState({ kind: "loading" });
    apiGet<HealthResponse>("/api/health")
      .then((data) => setState({ kind: "ok", status: data.status }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  };

  useEffect(check, []);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md w-full space-y-4 text-center">
        <h1 className="text-3xl font-semibold">What Should I Play?</h1>
        <p className="text-muted-foreground">Foundation health check.</p>
        <div className="rounded-md border border-border p-4">
          {state.kind === "loading" && <p>Checking backend…</p>}
          {state.kind === "ok" && (
            <p className="text-green-600">Backend reachable. Status: {state.status}</p>
          )}
          {state.kind === "error" && (
            <p className="text-red-600">Backend unreachable: {state.message}</p>
          )}
        </div>
        <Button onClick={check} variant="outline">
          Re-check
        </Button>
      </div>
    </div>
  );
}
