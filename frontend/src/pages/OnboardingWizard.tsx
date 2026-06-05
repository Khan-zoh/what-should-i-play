import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { setOnboarding } from "@/lib/api";
import { Button } from "@/components/ui/button";
import WelcomeStep from "@/components/onboarding/WelcomeStep";
import ConnectStep from "@/components/onboarding/ConnectStep";
import PreferencesStep from "@/components/onboarding/PreferencesStep";

type Step = "welcome" | "connect" | "preferences";
const ORDER: Step[] = ["welcome", "connect", "preferences"];

export default function OnboardingWizard() {
  const [step, setStep] = useState<Step>("welcome");
  const navigate = useNavigate();

  const complete = async () => {
    await setOnboarding(true);
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-6 py-3">
          <span className="text-sm text-muted-foreground">
            Step {ORDER.indexOf(step) + 1} of {ORDER.length}
          </span>
          <Button variant="ghost" size="sm" onClick={complete}>
            Skip setup
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-6 py-12">
        {step === "welcome" && <WelcomeStep onNext={() => setStep("connect")} />}
        {step === "connect" && (
          <ConnectStep onNext={() => setStep("preferences")} />
        )}
        {step === "preferences" && <PreferencesStep onFinish={complete} />}
      </main>
    </div>
  );
}
