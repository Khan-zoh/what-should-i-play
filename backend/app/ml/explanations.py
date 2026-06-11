"""Pure reason_code -> sentence templating. No LLM (that is a later sub-plan)."""
from __future__ import annotations


def explain(reason_codes: list[str]) -> str:
    liked = [c.split(":", 1)[1] for c in reason_codes if c.startswith("MATCHES_LIKED_GENRE:")]
    clauses: list[str] = []

    if "OWNED_AND_UNPLAYED" in reason_codes:
        clauses.append("is unplayed in your library")
    if liked:
        clauses.append(f"matches genres you like ({', '.join(liked)})")
    if any(c.startswith("SIMILAR_TO_HIGH_RATED:") for c in reason_codes):
        clauses.append("resembles games you rated highly")
    if "HIGH_CRITIC_SCORE" in reason_codes:
        clauses.append("reviews well with critics")
    if "BACKLOG_PRIORITY" in reason_codes:
        clauses.append("is in your backlog")

    if not clauses:
        clauses.append("is in your library")

    return "Recommended because it " + ", ".join(clauses) + "."
