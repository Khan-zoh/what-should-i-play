"""Owns the embedding lifecycle: builds input text, runs the encoder, persists
vectors. The encoder (torch-heavy) is injected; tests use a fake, and the real
sentence-transformers import happens lazily so the [ml] extra stays optional.

Deliberately NOT coupled to the Steam sync (Codex debate, D3/D5): embeddings are
rebuilt via their own endpoint, and a failure here never breaks an import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from app.db.repositories import (
    GameEmbeddingRepository,
    GameTagRepository,
    LibraryEntryRepository,
)

# Bump when build_input_text changes: vectors embed the template, so a template
# change must produce NEW rows (composite revision key), not silently reuse old ones.
TEXT_TEMPLATE_VERSION = 1


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray:  # (n, dim) float32
        ...


def embedding_revision(model_name: str) -> str:
    """Composite identity for stored vectors: model short-name + text-template rev."""
    short = model_name.split("/")[-1]
    return f"{short}|t{TEXT_TEMPLATE_VERSION}"


def build_input_text(*, name: str, summary: str | None, tags: list[str]) -> str:
    return f"{name} - {summary or ''} | tags: {', '.join(sorted(tags))}"


def load_real_encoder(model_name: str) -> Encoder:
    """Lazy-loads sentence-transformers; clear guidance when the extra is absent."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers is not installed. Embeddings need the ml extra: "
            'pip install -e .[ml] (from the backend directory).'
        ) from e

    model = SentenceTransformer(model_name)

    class _STEncoder:
        def encode(self, texts: list[str]) -> np.ndarray:
            out = model.encode(texts, normalize_embeddings=True)
            return np.asarray(out, dtype=np.float32)

    return _STEncoder()


@dataclass(frozen=True)
class EmbedReport:
    model: str
    attempted: int = 0
    embedded: int = 0
    skipped_existing: int = 0
    failed: list[dict] = field(default_factory=list)


class EmbeddingService:
    def __init__(
        self,
        *,
        encoder: Encoder,
        model_name: str,
        library: LibraryEntryRepository,
        tags: GameTagRepository,
        embeddings: GameEmbeddingRepository,
    ) -> None:
        self._encoder = encoder
        self._revision = embedding_revision(model_name)
        self._library = library
        self._tags = tags
        self._embeddings = embeddings

    def embed_missing(self, *, force: bool = False) -> EmbedReport:
        rows = self._library.list_all_with_games()
        all_ids = [g.id for _entry, g in rows]
        if force:
            target_ids = all_ids
        else:
            target_ids = self._embeddings.missing_game_ids(
                all_ids, model_name=self._revision
            )
        skipped = len(all_ids) - len(target_ids)
        if not target_ids:
            return EmbedReport(
                model=self._revision, attempted=0, embedded=0, skipped_existing=skipped
            )

        tag_map = self._tags.tags_by_game(target_ids)
        games_by_id = {g.id: g for _entry, g in rows}
        ordered = sorted(target_ids)
        texts = []
        for gid in ordered:
            g = games_by_id[gid]
            kinds = tag_map.get(gid, {})
            tags_flat = sorted(kinds.get("genre", set()) | kinds.get("theme", set()))
            texts.append(build_input_text(name=g.name, summary=g.summary, tags=tags_flat))

        try:
            vectors = self._encoder.encode(texts)
        except Exception as e:  # report, never raise: embeddings are an enhancement
            return EmbedReport(
                model=self._revision,
                attempted=len(ordered),
                embedded=0,
                skipped_existing=skipped,
                failed=[{"game_id": gid, "error": str(e)} for gid in ordered],
            )

        for gid, vec in zip(ordered, vectors):
            self._embeddings.upsert(game_id=gid, model_name=self._revision, vector=vec)
        return EmbedReport(
            model=self._revision,
            attempted=len(ordered),
            embedded=len(ordered),
            skipped_existing=skipped,
        )
