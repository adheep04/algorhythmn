"""External service clients for Spotify and OpenAI."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests
from anthropic import Anthropic
from anthropic._exceptions import APIStatusError

from . import cache, config, env, utils
from .candidates_gen import LLMClientProtocol as TasteLLMProtocol, SpotifyClientProtocol as TasteSpotifyProtocol
from .filter_candidates import LLMClientProtocol as RankingLLMProtocol, SpotifyClientProtocol as RankingSpotifyProtocol
from .models import TasteProfile

# Shared type aliases
LLMClientInterface = TasteLLMProtocol
SpotifyClientInterface = TasteSpotifyProtocol


@dataclass
class ClaudeLLMClient(LLMClientInterface, RankingLLMProtocol):
    """LLM implementation using Claude's Responses API."""

    api_key: str
    taste_profile_model: str = "claude-3-5-sonnet-20241022"
    query_expansion_model: str = "claude-3-5-sonnet-20241022"
    subjective_scoring_model: str = "claude-3-haiku-20240307"
    max_retries: int = 3

    def __post_init__(self) -> None:
        env.load_env()
        self._client = Anthropic(api_key=self.api_key)

    # Taste profile extraction -------------------------------------------------
    def generate_taste_profile(self, preferences: Dict[str, Sequence[str]]) -> Dict[str, Any]:
        prompt = self._build_preference_prompt(preferences)
        response = self._call_claude(
            model=self.taste_profile_model,
            system_prompt=(
                "You are a music taste analyst. Respond using valid JSON with keys: "
                "genres, scenes, moods, liked_descriptors, avoided_descriptors, era_preferences."
            ),
            user_content=prompt,
        )
        return response

    def expand_queries(
        self, taste_profile: TasteProfile, base_queries: Sequence[str]
    ) -> Sequence[str]:
        prompt = (
            "Given this taste profile and existing queries, suggest additional search queries "
            "that would surface underground or emerging artists. Make them diverse and non-redundant."
        )
        payload = {
            "taste_profile": taste_profile.raw or {
                "genres": taste_profile.genres,
                "scenes": taste_profile.scenes,
                "moods": taste_profile.moods,
            },
            "base_queries": list(base_queries),
        }
        response = self._call_claude(
            model=self.query_expansion_model,
            system_prompt="You are a music discovery strategist. Respond with JSON containing a 'queries' array.",
            user_content=json.dumps({"instruction": prompt, "context": payload}),
        )
        queries = response.get("queries", [])
        return queries

    def score_subjective_dimensions(
        self, artist_name: str, context: Dict[str, Any]
    ) -> Dict[str, float]:
        payload = {
            "artist": artist_name,
            "dimensions": config.SUBJECTIVE_DIMENSIONS,
            "taste_profile": context.get("taste_profile"),
            "notes": "Score each dimension from 0 to 1 where 0 is absent and 1 is extreme.",
        }
        response = self._call_claude(
            model=self.subjective_scoring_model,
            system_prompt=(
                "You evaluate artists on subjective attributes. Respond with JSON containing keys: "
                f"{', '.join(config.SUBJECTIVE_DIMENSIONS)}."
            ),
            user_content=json.dumps(payload),
        )
        return {
            dim: utils.clamp(float(response.get(dim, 0.0)))
            for dim in config.SUBJECTIVE_DIMENSIONS
        }

    # Internal helpers -------------------------------------------------------
    def _call_claude(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self._client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                    max_tokens=1024,
                )
                if not response.content:
                    raise RuntimeError("Empty response from Claude")
                text_chunks: List[str] = []
                for block in response.content:
                    if getattr(block, "type", "") == "text" and getattr(block, "text", None):
                        text_chunks.append(block.text)
                content_text = "".join(text_chunks).strip()
                if not content_text:
                    raise RuntimeError("Claude response contained no text content")
                return _safe_json_loads(content_text)
            except APIStatusError as error:
                last_error = error
                if error.status_code in {429, 500, 503} and attempt + 1 < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except Exception as error:
                last_error = error
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Claude call failed after {self.max_retries} attempts: {last_error}")

    def _build_preference_prompt(self, preferences: Dict[str, Sequence[str]]) -> str:
        payload = {
            bucket: list(values)
            for bucket, values in preferences.items()
            if values
        }
        return json.dumps({"preferences": payload})


class SpotifyAPIClient(SpotifyClientInterface, RankingSpotifyProtocol):
    """Spotify Web API client supporting candidate generation and ranking needs."""

    token_url = "https://accounts.spotify.com/api/token"
    api_base = "https://api.spotify.com/v1"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        market: str = "US",
        session: Optional[requests.Session] = None,
    ) -> None:
        env.load_env()
        self.client_id = client_id
        self.client_secret = client_secret
        self.market = market
        self.session = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # Candidate generation methods -------------------------------------------
    def search_artists(self, query: str, limit: int = config.MAX_RESULTS_PER_QUERY) -> List[Dict[str, Any]]:
        params = {"q": query, "type": "artist", "limit": limit}
        data = self._request("GET", "/search", params=params)
        return data.get("artists", {}).get("items", [])

    def get_related_artists(self, artist_id: str) -> List[Dict[str, Any]]:
        try:
            data = self._request("GET", f"/artists/{artist_id}/related-artists")
        except requests.HTTPError as error:  # type: ignore[attr-defined]
            if getattr(error.response, "status_code", None) == 404:
                return []
            raise
        return data.get("artists", [])

    def get_artist_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        results = self.search_artists(name, limit=5)
        target = utils.normalize_name(name)
        for item in results:
            if utils.normalize_name(item.get("name", "")) == target:
                return item
        return results[0] if results else None

    def get_artist(self, artist_id: str) -> Optional[Dict[str, Any]]:
        if not artist_id:
            return None
        try:
            return self._request("GET", f"/artists/{artist_id}")
        except requests.HTTPError as error:  # type: ignore[attr-defined]
            if getattr(error.response, "status_code", None) == 404:
                return None
            raise

    # Ranking methods -------------------------------------------------------
    def get_artist_audio_features(self, artist_id: str) -> Dict[str, float]:
        try:
            top_tracks_response = self._request(
                "GET",
                f"/artists/{artist_id}/top-tracks",
                params={"market": self.market},
            )
        except requests.HTTPError as error:  # type: ignore[attr-defined]
            if getattr(error.response, "status_code", None) == 403:
                return {}
            raise
        top_tracks = top_tracks_response.get("tracks", [])
        track_ids = [track.get("id") for track in top_tracks[:5] if track.get("id")]
        if not track_ids:
            return {}

        try:
            features_response = self._request(
                "GET",
                "/audio-features",
                params={"ids": ",".join(track_ids)},
            )
        except requests.HTTPError as error:  # type: ignore[attr-defined]
            if getattr(error.response, "status_code", None) == 403:
                return {}
            raise
        features = features_response.get("audio_features", [])
        if not features:
            return {}

        aggregated: Dict[str, float] = {
            dimension: 0.0 for dimension in config.SPOTIFY_AUDIO_FEATURE_MAP
        }
        counts = {dimension: 0 for dimension in config.SPOTIFY_AUDIO_FEATURE_MAP}
        for feature in features:
            for dimension, (key, transform) in config.SPOTIFY_AUDIO_FEATURE_MAP.items():
                value = feature.get(key)
                if value is None:
                    continue
                numeric = float(value)
                if transform:
                    numeric = transform(numeric)
                aggregated[dimension] += numeric
                counts[dimension] += 1

        averaged = {}
        for dimension, total in aggregated.items():
            count = counts[dimension]
            if count:
                averaged[dimension] = round(total / count, 4)
        return averaged

    # Internal helpers -------------------------------------------------------
    def _ensure_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token
        response = requests.post(
            self.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._token_expires_at = now + expires_in - 30
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        retry: int = 0,
    ) -> Dict[str, Any]:
        token = self._ensure_token()
        url = f"{self.api_base}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        response = self.session.request(method, url, headers=headers, params=params)
        if response.status_code == 401 and retry < 1:
            # token likely expired; refresh and retry once
            self._token = None
            return self._request(method, path, params=params, retry=retry + 1)
        response.raise_for_status()
        return response.json()


def build_live_clients(
    *,
    cache_client: Optional[cache.InMemoryCache] = None,
    spotify_market: str = "US",
    taste_profile_model: str = "claude-3-5-sonnet-20241022",
    query_expansion_model: str = "claude-3-5-sonnet-20241022",
    subjective_model: str = "claude-3-haiku-20240307",
) -> Dict[str, Any]:
    """Factory helper that wires OpenAI and Spotify clients using .env keys."""

    env.load_env()
    spotify_id = env.require({"SPOTIFY_CLIENT_ID": "", "SPOTIFY_CLIENT_SECRET": ""})
    claude_key = env.require({"CLAUDE_API_KEY": ""})

    spotify_client = SpotifyAPIClient(
        client_id=spotify_id["SPOTIFY_CLIENT_ID"],
        client_secret=spotify_id["SPOTIFY_CLIENT_SECRET"],
        market=spotify_market,
    )
    llm_client = ClaudeLLMClient(
        api_key=claude_key["CLAUDE_API_KEY"],
        taste_profile_model=taste_profile_model,
        query_expansion_model=query_expansion_model,
        subjective_scoring_model=subjective_model,
    )
    return {
        "spotify_client": spotify_client,
        "llm_client": llm_client,
        "cache_client": cache_client or cache.InMemoryCache(),
    }


def _safe_json_loads(payload: str) -> Dict[str, Any]:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(payload[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise
