export interface OnboardingErrorMessage {
  title: string;
  guidance: string;
  allowIdReentry: boolean;
}

export function messageForErrorCode(code: string | null): OnboardingErrorMessage {
  switch (code) {
    case "private_profile":
      return {
        title: "Your Steam profile is private",
        guidance:
          "Open Steam, go to Edit Profile then Privacy Settings, and set Game Details to Public. Then retry.",
        allowIdReentry: false,
      };
    case "invalid_steamid":
      return {
        title: "That Steam ID didn't work",
        guidance: "Double-check your 17-digit Steam ID and try again.",
        allowIdReentry: true,
      };
    case "rate_limited":
      return {
        title: "Steam is busy right now",
        guidance: "Steam is rate-limiting requests. Wait a moment, then retry.",
        allowIdReentry: false,
      };
    case "steam_auth":
      return {
        title: "Server Steam API key problem",
        guidance:
          "The Steam API key in backend/.env is missing or invalid. Fix it on the server, then retry.",
        allowIdReentry: false,
      };
    default:
      return {
        title: "Import failed",
        guidance: "Something went wrong talking to Steam. Retry, or skip for now.",
        allowIdReentry: false,
      };
  }
}
