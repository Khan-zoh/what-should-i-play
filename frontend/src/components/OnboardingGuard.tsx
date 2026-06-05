import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { getOnboarding } from "@/lib/api";

export default function OnboardingGuard({ children }: { children: ReactNode }) {
  const [checked, setChecked] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    getOnboarding()
      .then((status) => {
        if (!status.completed && location.pathname !== "/onboarding") {
          navigate("/onboarding", { replace: true });
        }
      })
      .catch(() => {
        // If status can't be read, fail open and let the app render.
      })
      .finally(() => setChecked(true));
    // Run once on mount; redirect decision uses the entry pathname.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );
  }
  return <>{children}</>;
}
