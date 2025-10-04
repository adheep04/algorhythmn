"""Filtering and ranking pipeline for artist candidates."""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from . import cache, config, models, utils


class LLMClientProtocol(Protocol):
    """Protocol for subjective dimension scoring via LLM."""

    def score_subjective_dimensions(
        self, artist_name: str, context: Dict[str, Any]
    ) -> Dict[str, float]:
        ...


class SpotifyClientProtocol(Protocol):
    """Protocol for Spotify feature access used during ranking."""

    def get_artist_audio_features(self, artist_id: str) -> Dict[str, float]:
        ...

    def get_artist_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        ...

    def get_artist(self, artist_id: str) -> Optional[Dict[str, Any]]:
        ...


def rank_candidates(
    preferences: Dict[str, Iterable[str]],
    candidate_pool: Sequence[models.ArtistCandidate],
    *,
    taste_profile: Optional[models.TasteProfile] = None,
    llm_client: Optional[LLMClientProtocol] = None,
    spotify_client: Optional[SpotifyClientProtocol] = None,
    cache_client: Optional[cache.InMemoryCache] = None,
    logger: Optional[Any] = None,
) -> models.RecommendationPayload:
    """Rank the provided candidate pool and return recommendations."""

    trimmed_preferences, _ = _normalize_preferences(preferences)
    taste_profile = taste_profile or _fallback_taste_profile(trimmed_preferences)

    loved_embeddings = _build_reference_embeddings(
        trimmed_preferences["love"],
        taste_profile,
        llm_client,
        spotify_client,
        cache_client,
    )
    hated_embeddings = _build_reference_embeddings(
        trimmed_preferences["hate"],
        taste_profile,
        llm_client,
        spotify_client,
        cache_client,
    )

    dimension_weights = _compute_dimension_weights(loved_embeddings, taste_profile)

    scored_candidates: List[models.ScoredCandidate] = []
    for candidate in candidate_pool:
        embedding = _ensure_candidate_embedding(
            candidate,
            taste_profile,
            llm_client,
            spotify_client,
            cache_client,
        )
        if not embedding:
            continue
        score = _score_candidate(
            candidate,
            embedding,
            loved_embeddings,
            hated_embeddings,
            dimension_weights,
        )
        scored_candidates.append(score)

    scored_candidates.sort(key=lambda item: item.aggregate_score, reverse=True)

    selected, diversity_score = _select_diverse_candidates(
        scored_candidates,
        dimension_weights,
        target=config.TARGET_RECOMMENDATIONS,
    )

    backlog = [candidate for candidate in scored_candidates if candidate not in selected]

    diagnostics = models.RankingDiagnostics(
        dimension_weights=dimension_weights,
        source_coverage=_calculate_source_coverage(candidate_pool),
        total_candidates=len(candidate_pool),
        filtered_candidates=len(scored_candidates),
        diversity_score=diversity_score,
    )

    metadata = {
        "taste_profile": taste_profile.raw or {
            "genres": taste_profile.genres,
            "scenes": taste_profile.scenes,
            "moods": taste_profile.moods,
        },
        "dimension_order": config.DIMENSIONS,
    }

    if logger:
        logger.debug(
            "ranking_complete",
            extra={
                "recommendations": len(selected),
                "backlog": len(backlog),
                "diversity_score": diversity_score,
            },
        )

    return models.RecommendationPayload(
        recommendations=selected,
        backlog=backlog,
        metadata=metadata,
        diagnostics=diagnostics,
    )


def _normalize_preferences(
    preferences: Dict[str, Iterable[str]]
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    trimmed: Dict[str, List[str]] = {}
    normalized: Dict[str, List[str]] = {}
    for bucket in ("love", "like", "dislike", "hate"):
        values = preferences.get(bucket, []) if preferences else []
        trimmed_values = [str(item).strip() for item in values if str(item).strip()]
        trimmed[bucket] = trimmed_values
        normalized[bucket] = [utils.normalize_name(value) for value in trimmed_values]
    return trimmed, normalized


def _fallback_taste_profile(preferences: Dict[str, List[str]]) -> models.TasteProfile:
    loved = preferences.get("love") or []
    likes = preferences.get("like") or []
    descriptors = loved + likes
    return models.TasteProfile(
        genres=[descriptor for descriptor in descriptors if descriptor],
        liked_descriptors=["melodic"],
        avoided_descriptors=[],
        moods=["energetic"],
        raw={"fallback": True},
    )


def _build_reference_embeddings(
    artist_names: Sequence[str],
    taste_profile: models.TasteProfile,
    llm_client: Optional[LLMClientProtocol],
    spotify_client: Optional[SpotifyClientProtocol],
    cache_client: Optional[cache.InMemoryCache],
) -> List[models.ArtistEmbedding]:
    embeddings: List[models.ArtistEmbedding] = []
    for name in artist_names:
        embedding = models.ArtistEmbedding()
        if spotify_client:
            details = spotify_client.get_artist_by_name(name)
            if details and details.get("id"):
                audio_features = _get_audio_features(
                    details["id"],
                    spotify_client,
                    cache_client,
                )
                embedding.update({
                    dimension: utils.clamp(audio_features.get(feature_key, 0.0))
                    for dimension, (feature_key, _) in config.SPOTIFY_AUDIO_FEATURE_MAP.items()
                })
        if llm_client:
            subjective = llm_client.score_subjective_dimensions(
                name,
                {
                    "taste_profile": taste_profile.raw,
                    "dimensions": config.SUBJECTIVE_DIMENSIONS,
                },
            )
            embedding.update({dim: utils.clamp(subjective.get(dim, 0.0)) for dim in config.SUBJECTIVE_DIMENSIONS})
        if embedding.values:
            embeddings.append(embedding)
    return embeddings


def _compute_dimension_weights(
    embeddings: Sequence[models.ArtistEmbedding],
    taste_profile: models.TasteProfile,
) -> Dict[str, float]:
    epsilon = 1e-6
    if not embeddings:
        return {dimension: 1.0 / len(config.DIMENSIONS) for dimension in config.DIMENSIONS}

    variances: Dict[str, float] = {}
    for dimension in config.DIMENSIONS:
        values = [embedding.values.get(dimension, 0.0) for embedding in embeddings]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / max(len(values) - 1, 1)
        variances[dimension] = variance

    weights = {}
    for dimension, variance in variances.items():
        importance = 1.0 / (variance + epsilon)
        if not math.isfinite(importance):
            importance = 0.0
        weights[dimension] = importance

    total = sum(weights.values())
    if total <= 0:
        return {dimension: 1.0 / len(config.DIMENSIONS) for dimension in config.DIMENSIONS}

    return {dimension: weight / total for dimension, weight in weights.items()}


def _ensure_candidate_embedding(
    candidate: models.ArtistCandidate,
    taste_profile: models.TasteProfile,
    llm_client: Optional[LLMClientProtocol],
    spotify_client: Optional[SpotifyClientProtocol],
    cache_client: Optional[cache.InMemoryCache],
) -> Optional[models.ArtistEmbedding]:
    embedding = candidate.embedding or models.ArtistEmbedding()

    if spotify_client and candidate.spotify_id:
        audio_features = candidate.audio_features
        if not audio_features:
            audio_features = _get_audio_features(
                candidate.spotify_id,
                spotify_client,
                cache_client,
            )
            candidate.audio_features = audio_features
        embedding.update({
            dimension: utils.clamp(audio_features.get(feature_key, 0.0))
            for dimension, (feature_key, _) in config.SPOTIFY_AUDIO_FEATURE_MAP.items()
        })

    if llm_client:
        subjective = llm_client.score_subjective_dimensions(
            candidate.name,
            {
                "source": candidate.metadata.get("sources"),
                "taste_profile": taste_profile.raw,
                "dimensions": config.SUBJECTIVE_DIMENSIONS,
            },
        )
        embedding.update({dim: utils.clamp(subjective.get(dim, 0.0)) for dim in config.SUBJECTIVE_DIMENSIONS})

    if not embedding.values:
        candidate.embedding = None
        return None

    candidate.embedding = embedding
    return embedding


def _get_audio_features(
    artist_id: str,
    spotify_client: Optional[SpotifyClientProtocol],
    cache_client: Optional[cache.InMemoryCache],
) -> Dict[str, float]:
    if not spotify_client or not artist_id:
        return {}
    namespace = config.CACHE_NAMESPACES["audio_features"]
    cache_key = cache.build_cache_key(artist_id)
    if cache_client:
        cached = cache_client.get(namespace, cache_key)
        if cached:
            return cached
    features = spotify_client.get_artist_audio_features(artist_id)
    if cache_client:
        cache_client.set(namespace, cache_key, features)
    return features


def _score_candidate(
    candidate: models.ArtistCandidate,
    embedding: models.ArtistEmbedding,
    loved_embeddings: Sequence[models.ArtistEmbedding],
    hated_embeddings: Sequence[models.ArtistEmbedding],
    weights: Dict[str, float],
) -> models.ScoredCandidate:
    love_distance, hate_distance = _compute_reference_distances(
        embedding,
        loved_embeddings,
        hated_embeddings,
        weights,
    )
    similarity = 1.0 / (love_distance + 1e-6) if love_distance is not None else 0.0
    penalty = 1.0 / (hate_distance + 1e-6) if hate_distance is not None else 0.0

    if candidate.is_flagged("hated"):
        penalty += 1.0
    elif candidate.is_flagged("disliked"):
        penalty += 0.5

    aggregate = similarity - penalty

    rationale_parts = [
        f"closest loved distance={love_distance:.3f}" if love_distance is not None else "no loved reference",
        f"closest hated distance={hate_distance:.3f}" if hate_distance is not None else "no hated reference",
    ]
    if candidate.flags:
        rationale_parts.append(f"flags={','.join(sorted(candidate.flags))}")
    rationale = "; ".join(rationale_parts)

    return models.ScoredCandidate(
        candidate=candidate,
        similarity_score=similarity,
        penalty_score=penalty,
        aggregate_score=aggregate,
        rationale=rationale,
    )


def _compute_reference_distances(
    embedding: models.ArtistEmbedding,
    loved_embeddings: Sequence[models.ArtistEmbedding],
    hated_embeddings: Sequence[models.ArtistEmbedding],
    weights: Dict[str, float],
) -> Tuple[Optional[float], Optional[float]]:
    love_distance = None
    hate_distance = None

    for reference in loved_embeddings:
        distance = _weighted_distance(embedding, reference, weights)
        if love_distance is None or distance < love_distance:
            love_distance = distance

    for reference in hated_embeddings:
        distance = _weighted_distance(embedding, reference, weights)
        if hate_distance is None or distance < hate_distance:
            hate_distance = distance

    return love_distance, hate_distance


def _weighted_distance(
    a: models.ArtistEmbedding, b: models.ArtistEmbedding, weights: Dict[str, float]
) -> float:
    total = 0.0
    for dimension, weight in weights.items():
        diff = a.values.get(dimension, 0.0) - b.values.get(dimension, 0.0)
        total += weight * diff * diff
    return math.sqrt(max(total, 0.0))


def _select_diverse_candidates(
    scored_candidates: Sequence[models.ScoredCandidate],
    weights: Dict[str, float],
    *,
    target: int,
) -> Tuple[List[models.ScoredCandidate], float]:
    if not scored_candidates:
        return [], 0.0

    selected: List[models.ScoredCandidate] = []
    selected_sources: set = set()
    remaining = list(scored_candidates)
    lambda_diversity = utils.clamp(config.DIVERSITY_WEIGHT, 0.0, 1.0)

    aggregates = [candidate.aggregate_score for candidate in scored_candidates]
    min_score = min(aggregates)
    max_score = max(aggregates)
    score_range = max(max_score - min_score, 1e-6)

    while remaining and len(selected) < target:
        best_candidate: Optional[models.ScoredCandidate] = None
        best_score = float("-inf")
        for candidate in remaining:
            if candidate.candidate.is_flagged("hated"):
                continue
            base = (candidate.aggregate_score - min_score) / score_range
            if not selected:
                diversity_component = 1.0
            else:
                distances = [
                    _weighted_distance(
                        candidate.candidate.embedding,
                        existing.candidate.embedding,
                        weights,
                    )
                    for existing in selected
                ]
                diversity_component = sum(distances) / len(distances)
                diversity_component = utils.clamp(diversity_component, 0.0, 1.0)
            mmr = (1 - lambda_diversity) * base + lambda_diversity * diversity_component
            candidate_sources = _candidate_sources(candidate.candidate)
            if not selected_sources.intersection(candidate_sources):
                mmr += 0.05
            if candidate.candidate.is_flagged("disliked"):
                mmr -= 0.2
            if mmr > best_score:
                best_candidate = candidate
                best_score = mmr
        if not best_candidate:
            break
        selected.append(best_candidate)
        remaining.remove(best_candidate)
        selected_sources |= _candidate_sources(best_candidate.candidate)

    if not selected:
        return [], 0.0

    if len(selected) == 1:
        diversity_score = 1.0
    else:
        pair_distances = []
        for idx, candidate in enumerate(selected):
            for other in selected[idx + 1 :]:
                pair_distances.append(
                    _weighted_distance(
                        candidate.candidate.embedding,
                        other.candidate.embedding,
                        weights,
                    )
                )
        diversity_score = sum(pair_distances) / len(pair_distances)
        diversity_score = utils.clamp(diversity_score, 0.0, 1.0)

    return selected, diversity_score


def _calculate_source_coverage(candidate_pool: Sequence[models.ArtistCandidate]) -> Dict[str, int]:
    coverage: Dict[str, int] = {}
    for candidate in candidate_pool:
        sources = candidate.metadata.get("sources", {candidate.source})
        if isinstance(sources, set):
            source_iterable = sources
        else:
            source_iterable = {candidate.source}
        for source in source_iterable:
            coverage[source] = coverage.get(source, 0) + 1
    return coverage


def _candidate_sources(candidate: models.ArtistCandidate) -> set:
    sources = candidate.metadata.get("sources")
    if isinstance(sources, set) and sources:
        return {str(source) for source in sources}
    return {candidate.source}
