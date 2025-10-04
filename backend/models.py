"""Domain models for the recommendation backend."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from . import config


@dataclass
class TasteProfile:
    """Structured representation of the user's musical preferences."""

    genres: List[str] = field(default_factory=list)
    scenes: List[str] = field(default_factory=list)
    moods: List[str] = field(default_factory=list)
    liked_descriptors: List[str] = field(default_factory=list)
    avoided_descriptors: List[str] = field(default_factory=list)
    era_preferences: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_llm_response(cls, response: Dict[str, Any]) -> "TasteProfile":
        """Normalize an LLM taste profile payload."""

        def _pluck(key: str) -> List[str]:
            value = response.get(key, [])
            if isinstance(value, str):
                return [value]
            if isinstance(value, Iterable):
                return [str(item) for item in value if str(item).strip()]
            return []

        profile = cls(
            genres=_pluck("genres"),
            scenes=_pluck("scenes"),
            moods=_pluck("moods"),
            liked_descriptors=_pluck("liked_descriptors"),
            avoided_descriptors=_pluck("avoided_descriptors"),
            era_preferences=_pluck("era_preferences"),
            raw=response,
        )
        return profile

    def stable_signature(self) -> str:
        """Generate a stable string representation for caching."""

        parts = [
            "|".join(sorted(set(self.genres))),
            "|".join(sorted(set(self.scenes))),
            "|".join(sorted(set(self.moods))),
            "|".join(sorted(set(self.liked_descriptors))),
            "|".join(sorted(set(self.avoided_descriptors))),
            "|".join(sorted(set(self.era_preferences))),
        ]
        return "::".join(parts)


@dataclass
class ArtistEmbedding:
    """Embedding values for an artist across the canonical dimensions."""

    values: Dict[str, float] = field(default_factory=dict)

    def as_vector(self, dimensions: Sequence[str] = config.DIMENSIONS) -> List[float]:
        """Return embedding values ordered by the configured dimension list."""

        return [float(self.values.get(dimension, 0.0)) for dimension in dimensions]

    def update(self, updates: Dict[str, float]) -> None:
        for key, value in updates.items():
            if key in config.DIMENSIONS:
                self.values[key] = float(value)


@dataclass
class ArtistCandidate:
    """Represents an artist uncovered during candidate generation."""

    spotify_id: str
    name: str
    popularity: int
    source: str
    source_query: str
    genres: List[str] = field(default_factory=list)
    markets: Set[str] = field(default_factory=set)
    audio_features: Dict[str, float] = field(default_factory=dict)
    followers: int = 0
    embedding: Optional[ArtistEmbedding] = None
    flags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized_name(self) -> str:
        """Case-folded normalized name used for deduplication."""

        return self.name.strip().casefold()

    def tag(self, label: str) -> None:
        self.flags.add(label)

    def is_flagged(self, label: str) -> bool:
        return label in self.flags


@dataclass
class ScoredCandidate:
    """Holds scoring results for a candidate."""

    candidate: ArtistCandidate
    similarity_score: float
    penalty_score: float
    aggregate_score: float
    rationale: str


@dataclass
class RankingDiagnostics:
    """Diagnostics produced during ranking."""

    dimension_weights: Dict[str, float] = field(default_factory=dict)
    source_coverage: Dict[str, int] = field(default_factory=dict)
    total_candidates: int = 0
    filtered_candidates: int = 0
    diversity_score: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class RecommendationPayload:
    """Structured payload returned to the frontend."""

    recommendations: List[ScoredCandidate]
    backlog: List[ScoredCandidate]
    metadata: Dict[str, Any]
    diagnostics: RankingDiagnostics


@dataclass
class CandidateGenerationResult:
    """Output from the candidate generation phase."""

    taste_profile: TasteProfile
    candidates: List[ArtistCandidate]
    diagnostics: Dict[str, Any] = field(default_factory=dict)
