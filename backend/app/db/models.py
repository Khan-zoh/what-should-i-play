"""Stable-spine ORM models for What Should I Play.

Subsystem-specific tables (quiz_sessions, model_runs, play_sessions) live in
their own sub-plans and are added later via Alembic migrations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    igdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    steam_appid: Mapped[int | None] = mapped_column(
        Integer, unique=True, index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    store_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    critic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    steam_review_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    steam_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tags: Mapped[list[GameTag]] = relationship(back_populates="game", cascade="all, delete-orphan")
    embeddings: Mapped[list[GameEmbedding]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class GameEmbedding(Base):
    __tablename__ = "game_embeddings"
    __table_args__ = (UniqueConstraint("game_id", "model_name", name="uq_game_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    game: Mapped[Game] = relationship(back_populates="embeddings")


class GameTag(Base):
    __tablename__ = "game_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tag: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    # kind ∈ {"genre", "theme", "mechanic", "mood"}

    game: Mapped[Game] = relationship(back_populates="tags")


# ---------------------------------------------------------------------------
# User data
# ---------------------------------------------------------------------------


class LibraryEntry(Base):
    __tablename__ = "library_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "steam" | "manual"
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hours_played: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserGameState(Base):
    __tablename__ = "user_game_state"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # status ∈ {backlog, installed, currently_playing, completed, abandoned,
    #          wishlisted, hidden, not_interested, want_to_replay,
    #          multiplayer_only, tried_and_refunded}
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


VALID_GAME_STATUSES = frozenset(
    {
        "backlog",
        "installed",
        "currently_playing",
        "completed",
        "abandoned",
        "wishlisted",
        "hidden",
        "not_interested",
        "want_to_replay",
        "multiplayer_only",
        "tried_and_refunded",
    }
)


class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enjoyment: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5
    finished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class Preferences(Base):
    """Singleton row; we always read/write id=1."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    liked_genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    disliked_genres: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    liked_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    session_length_pref: Mapped[str] = mapped_column(String(16), default="any", nullable=False)
    difficulty_pref: Mapped[str] = mapped_column(String(16), default="any", nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True, nullable=False
    )
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    # surface ∈ {quiz_result, for_you, library_browse}
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filters_applied: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abstention_path: Mapped[str] = mapped_column(String(16), nullable=False)
    # abstention_path ∈ {heuristic, ridge, lgbm}
    cluster_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation_variant: Mapped[str] = mapped_column(String(16), nullable=False)
    # explanation_variant ∈ {templated, llm}

    shown_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_playing_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismiss_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # dismiss_reason ∈ {too_long, wrong_genre, too_expensive, wrong_platform,
    #                   already_played_elsewhere, not_interested}


class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "steam" | "igdb"
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "ok"|"partial"|"failed"
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class LLMCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
