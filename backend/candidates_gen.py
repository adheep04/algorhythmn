"""Candidate generation pipeline."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Set

from . import cache, config, models, utils


class LLMClientProtocol(Protocol):
    """Protocol for LLM interactions used in candidate generation."""

    def generate_taste_profile(self, preferences: Dict[str, Sequence[str]]) -> Dict[str, Any]:
        ...

    def expand_queries(
        self, taste_profile: models.TasteProfile, base_queries: Sequence[str]
    ) -> Sequence[str]:
        ...


class SpotifyClientProtocol(Protocol):
    """Protocol for Spotify data access used in candidate generation."""

    def search_artists(self, query: str, limit: int = config.MAX_RESULTS_PER_QUERY) -> List[Dict[str, Any]]:
        ...

    def get_related_artists(self, artist_id: str) -> List[Dict[str, Any]]:
        ...

    def get_artist_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        ...

    def get_artist(self, artist_id: str) -> Optional[Dict[str, Any]]:
        ...


@dataclass
class GenerationContext:
    preferences: Dict[str, List[str]]
    normalized_lists: Dict[str, List[str]]
    normalized_sets: Dict[str, Set[str]]
    taste_profile: models.TasteProfile
    queries: List[str]


def generate_candidates(
    preferences: Dict[str, Iterable[str]],
    llm_client: Optional[LLMClientProtocol],
    spotify_client: SpotifyClientProtocol,
    cache_client: Optional[cache.InMemoryCache] = None,
    *,
    enable_llm_query_expansion: bool = False,
    logger: Optional[Any] = None,
) -> models.CandidateGenerationResult:
    """Generate candidate artists for the user preferences."""

    preferences_dict = _normalize_preferences(preferences)
    taste_profile = _obtain_taste_profile(preferences_dict, llm_client, cache_client)
    queries = _generate_queries(
        taste_profile,
        preferences_dict,
        llm_client if enable_llm_query_expansion else None,
        cache_client,
    )

    normalized_lists = {
        bucket: [utils.normalize_name(value) for value in values]
        for bucket, values in preferences_dict.items()
    }
    normalized_sets = {bucket: set(values) for bucket, values in normalized_lists.items()}

    context = GenerationContext(
        preferences={key: list(vals) for key, vals in preferences_dict.items()},
        normalized_lists=normalized_lists,
        normalized_sets=normalized_sets,
        taste_profile=taste_profile,
        queries=queries,
    )

    candidate_map: Dict[str, models.ArtistCandidate] = {}
    diagnostics: Dict[str, Any] = {
        "queries": queries,
        "source_counts": defaultdict(int),
        "notes": [],
    }

    _ingest_query_candidates(context, candidate_map, diagnostics, spotify_client)
    _ingest_related_candidates(context, candidate_map, diagnostics, spotify_client)
    _ingest_cross_pollination(context, candidate_map, diagnostics, spotify_client)

    candidates = list(candidate_map.values())

    trimmed_count = 0
    if len(candidates) > config.TARGET_CANDIDATES:
        mandatory: List[models.ArtistCandidate] = []
        optional: List[models.ArtistCandidate] = []
        mandatory_keys = set()
        for candidate in candidates:
            if candidate.is_flagged("hated") or candidate.is_flagged("disliked"):
                mandatory.append(candidate)
                mandatory_keys.add(candidate.normalized_name())
            else:
                optional.append(candidate)

        optional.sort(key=lambda c: (c.popularity, c.name.casefold()))
        remaining_slots = max(config.TARGET_CANDIDATES - len(mandatory), 0)
        selected_optional = optional[:remaining_slots]

        # Ensure we don't exceed target but keep mandatory entries even if over
        trimmed_candidates = mandatory + selected_optional
        trimmed_count = len(candidates) - len(trimmed_candidates)
        candidates = trimmed_candidates

    diagnostics["total_candidates"] = len(candidates)
    diagnostics["unique_candidates"] = len(candidate_map)
    diagnostics["source_counts"] = dict(diagnostics["source_counts"])
    diagnostics["trimmed_count"] = trimmed_count

    if logger:
        logger.debug(
            "candidate_generation_complete",
            extra={
                "queries": len(queries),
                "candidates": len(candidates),
                "sources": diagnostics["source_counts"],
            },
        )

    return models.CandidateGenerationResult(
        taste_profile=taste_profile,
        candidates=candidates,
        diagnostics=diagnostics,
    )


def _normalize_preferences(preferences: Dict[str, Iterable[str]]) -> Dict[str, List[str]]:
    normalized = {}
    for bucket in ("love", "like", "dislike", "hate"):
        values = preferences.get(bucket, []) if preferences else []
        normalized[bucket] = [str(item).strip() for item in values if str(item).strip()]
    return normalized


def _obtain_taste_profile(
    preferences: Dict[str, List[str]],
    llm_client: Optional[LLMClientProtocol],
    cache_client: Optional[cache.InMemoryCache],
) -> models.TasteProfile:
    cache_key = utils.hash_preferences(preferences)
    namespace = config.CACHE_NAMESPACES["taste_profile"]

    if cache_client:
        cached = cache_client.get(namespace, cache_key)
        if cached:
            return cached

    if llm_client:
        response = llm_client.generate_taste_profile(preferences)
        profile = models.TasteProfile.from_llm_response(response)
    else:
        profile = _fallback_taste_profile(preferences)

    if cache_client:
        cache_client.set(namespace, cache_key, profile)
    return profile


def _fallback_taste_profile(preferences: Dict[str, List[str]]) -> models.TasteProfile:
    loved = preferences.get("love") or []
    likes = preferences.get("like") or []
    descriptors = loved + likes
    return models.TasteProfile(
        genres=descriptors,
        liked_descriptors=["melodic"],
        avoided_descriptors=[],
        moods=["energetic"],
        raw={"fallback": True},
    )


def _generate_queries(
    taste_profile: models.TasteProfile,
    preferences: Dict[str, List[str]],
    llm_client: Optional[LLMClientProtocol],
    cache_client: Optional[cache.InMemoryCache],
) -> List[str]:
    base_terms = list(dict.fromkeys(
        [term for term in (
            taste_profile.genres
            + taste_profile.scenes
            + taste_profile.moods
            + taste_profile.liked_descriptors
        ) if term]
    ))

    if not base_terms:
        base_terms = preferences.get("love", []) or preferences.get("like", [])
        base_terms = [term for term in base_terms if term]

    modifiers = ["underground", "experimental", "emerging", "new", "independent"]
    queries: List[str] = []
    for term in base_terms:
        for modifier in modifiers:
            query = f"{modifier} {term}".strip()
            if query not in queries:
                queries.append(query)
            if len(queries) >= config.MAX_QUERY_COUNT:
                break
        if len(queries) >= config.MAX_QUERY_COUNT:
            break

    if llm_client and hasattr(llm_client, "expand_queries") and cache_client:
        cache_key = cache.build_cache_key(
            "llm_query_expansion",
            taste_profile.stable_signature(),
        )
        expanded = cache_client.get(config.CACHE_NAMESPACES["search_results"], cache_key)
        if expanded is None:
            expanded = list(llm_client.expand_queries(taste_profile, queries))
            cache_client.set(config.CACHE_NAMESPACES["search_results"], cache_key, expanded)
        for query in expanded:
            if query not in queries and len(queries) < config.MAX_QUERY_COUNT:
                queries.append(query)

    if not queries:
        queries = ["underground experimental music"]
    return queries


def _ingest_query_candidates(
    context: GenerationContext,
    candidate_map: Dict[str, models.ArtistCandidate],
    diagnostics: Dict[str, Any],
    spotify_client: SpotifyClientProtocol,
) -> None:
    for query in context.queries:
        results = spotify_client.search_artists(query, limit=config.MAX_RESULTS_PER_QUERY)
        for payload in results:
            _maybe_record_candidate(
                payload,
                source="search",
                source_query=query,
                context=context,
                candidate_map=candidate_map,
                diagnostics=diagnostics,
                spotify_client=spotify_client,
            )


def _ingest_related_candidates(
    context: GenerationContext,
    candidate_map: Dict[str, models.ArtistCandidate],
    diagnostics: Dict[str, Any],
    spotify_client: SpotifyClientProtocol,
) -> None:
    loved_artists = context.preferences.get("love", [])
    for artist_name in loved_artists:
        details = spotify_client.get_artist_by_name(artist_name)
        if not details or not details.get("id"):
            diagnostics["notes"].append(f"missing_details:{artist_name}")
            continue
        related = spotify_client.get_related_artists(details["id"])
        for payload in related:
            _maybe_record_candidate(
                payload,
                source="related",
                source_query=artist_name,
                context=context,
                candidate_map=candidate_map,
                diagnostics=diagnostics,
                spotify_client=spotify_client,
            )


def _ingest_cross_pollination(
    context: GenerationContext,
    candidate_map: Dict[str, models.ArtistCandidate],
    diagnostics: Dict[str, Any],
    spotify_client: SpotifyClientProtocol,
) -> None:
    loved = context.preferences.get("love", [])
    if len(loved) < 2:
        return
    for artist_a, artist_b in combinations(loved, 2):
        query = f"{artist_a} {artist_b} fusion"
        results = spotify_client.search_artists(query, limit=10)
        for payload in results:
            _maybe_record_candidate(
                payload,
                source="cross",
                source_query=query,
                context=context,
                candidate_map=candidate_map,
                diagnostics=diagnostics,
                spotify_client=spotify_client,
            )


def _maybe_record_candidate(
    payload: Dict[str, Any],
    *,
    source: str,
    source_query: str,
    context: GenerationContext,
    candidate_map: Dict[str, models.ArtistCandidate],
    diagnostics: Dict[str, Any],
    spotify_client: SpotifyClientProtocol,
) -> None:
    candidate = _convert_payload(payload, source, source_query)
    if not candidate:
        return
    if candidate.popularity > config.POPULARITY_THRESHOLD:
        return

    _ensure_followers(candidate, spotify_client)
    if candidate.followers < config.MIN_FOLLOWERS_THRESHOLD:
        diagnostics.setdefault("notes", []).append(
            f"below_followers_threshold:{candidate.name}:{candidate.followers}"
        )
        return

    normalized = candidate.normalized_name()
    existing = candidate_map.get(normalized)
    if existing:
        existing.metadata.setdefault("source_queries", set()).add(source_query)
        existing.metadata.setdefault("sources", set()).add(source)
        existing.metadata.setdefault("spotify_ids", set()).add(candidate.spotify_id)
        existing.popularity = min(existing.popularity, candidate.popularity)
        existing.genres = sorted(set(existing.genres) | set(candidate.genres))
        existing.markets |= candidate.markets
        existing.followers = max(existing.followers, candidate.followers)
    else:
        candidate.metadata["sources"] = {source}
        candidate.metadata["source_queries"] = {source_query}
        candidate.metadata["spotify_ids"] = {candidate.spotify_id}
        _apply_preference_flags(candidate, context)
        candidate_map[normalized] = candidate
        diagnostics["source_counts"][source] += 1


def _convert_payload(
    payload: Dict[str, Any],
    source: str,
    source_query: str,
) -> Optional[models.ArtistCandidate]:
    if not payload:
        return None
    required = {"id", "name", "popularity"}
    if not required.issubset(payload):
        return None
    try:
        popularity = int(payload.get("popularity", 0))
    except (TypeError, ValueError):
        popularity = 0
    followers_raw = payload.get("followers") or {}
    try:
        followers = int(followers_raw.get("total", 0)) if isinstance(followers_raw, dict) else int(followers_raw)
    except (TypeError, ValueError):
        followers = 0
    candidate = models.ArtistCandidate(
        spotify_id=str(payload["id"]),
        name=str(payload["name"]),
        popularity=popularity,
        source=source,
        source_query=source_query,
        genres=list(payload.get("genres", []) or []),
        markets=set(payload.get("markets", []) or []),
        metadata={"raw": payload},
        followers=followers,
    )
    return candidate


def _apply_preference_flags(candidate: models.ArtistCandidate, context: GenerationContext) -> None:
    normalized = candidate.normalized_name()
    if normalized in context.normalized_sets.get("dislike", set()):
        candidate.tag("disliked")
    if normalized in context.normalized_sets.get("hate", set()):
        candidate.tag("hated")


def _ensure_followers(
    candidate: models.ArtistCandidate,
    spotify_client: SpotifyClientProtocol,
) -> None:
    if candidate.followers >= config.MIN_FOLLOWERS_THRESHOLD:
        return
    if not candidate.spotify_id:
        return
    details = spotify_client.get_artist(candidate.spotify_id)
    if not details:
        return
    followers_raw = details.get("followers") or {}
    try:
        followers = int(followers_raw.get("total", 0)) if isinstance(followers_raw, dict) else int(followers_raw)
    except (TypeError, ValueError):
        followers = 0
    candidate.followers = followers
