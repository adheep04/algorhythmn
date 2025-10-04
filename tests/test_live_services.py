import os

import pytest

from backend import cache, config, env, services
from backend.candidates_gen import generate_candidates
from backend.filter_candidates import rank_candidates
from backend.models import TasteProfile

env.load_env()

REQUIRED_KEYS = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "CLAUDE_API_KEY"]
LIVE_KEYS_PRESENT = all(key in os.environ for key in REQUIRED_KEYS)

skip_live = pytest.mark.skipif(
    not LIVE_KEYS_PRESENT,
    reason="Spotify/OpenAI API keys not configured in .env or environment",
)


@skip_live
def test_live_spotify_search_and_audio_features():
    clients = services.build_live_clients()
    spotify = clients["spotify_client"]

    results = spotify.search_artists("independent electronic", limit=5)
    assert results, "Expected at least one search result"

    first_artist = results[0]
    assert "id" in first_artist and "name" in first_artist

    related = spotify.get_related_artists(first_artist["id"])
    assert isinstance(related, list)

    try:
        audio_features = spotify.get_artist_audio_features(first_artist["id"])
    except Exception as error:
        if "403" in str(error) or "forbidden" in str(error).lower():
            pytest.skip("Spotify access forbidden for audio features")
        raise
    # Not all artists have top tracks, but when they do we expect numerical features
    if audio_features:
        for key, value in audio_features.items():
            assert key in config.SPOTIFY_AUDIO_FEATURE_MAP
            assert 0.0 <= value <= 1.0


@skip_live
def test_live_openai_taste_profile_and_scoring():
    clients = services.build_live_clients()
    llm = clients["llm_client"]

    preferences = {
        "love": ["Aphex Twin", "Boards of Canada"],
        "like": ["dark ambient"],
        "dislike": ["mainstream pop"],
    }
    try:
        profile_response = llm.generate_taste_profile(preferences)
    except RuntimeError as error:
        message = str(error).lower()
        if "insufficient_quota" in message or "quota" in message:
            pytest.skip("OpenAI quota exceeded")
        if "model_not_found" in message or "not supported" in message:
            pytest.skip("Requested OpenAI model unavailable")
        raise

    profile = TasteProfile.from_llm_response(profile_response)
    assert profile.genres

    try:
        subjective = llm.score_subjective_dimensions(
            "Aphex Twin",
            {"taste_profile": profile.raw},
        )
    except RuntimeError as error:
        message = str(error).lower()
        if "insufficient_quota" in message or "quota" in message:
            pytest.skip("OpenAI quota exceeded")
        if "model_not_found" in message or "not supported" in message:
            pytest.skip("Requested OpenAI model unavailable")
        raise
    assert set(subjective) == set(config.SUBJECTIVE_DIMENSIONS)


@skip_live
@pytest.mark.slow
def test_live_end_to_end_pipeline(monkeypatch):
    clients = services.build_live_clients()
    spotify = clients["spotify_client"]
    llm = clients["llm_client"]
    cache_client = clients["cache_client"]

    # Reduce outbound calls for the live test
    monkeypatch.setattr(config, "MAX_QUERY_COUNT", 6)
    monkeypatch.setattr(config, "MAX_RESULTS_PER_QUERY", 5)

    preferences = {
        "love": ["Aphex Twin", "Autechre"],
        "dislike": ["mainstream pop"],
        "hate": ["Ed Sheeran"],
    }
    try:
        generation = generate_candidates(
            preferences,
            llm_client=llm,
            spotify_client=spotify,
            cache_client=cache_client,
            enable_llm_query_expansion=False,
        )
    except RuntimeError as error:
        message = str(error).lower()
        if "insufficient_quota" in message or "quota" in message:
            pytest.skip("OpenAI quota exceeded")
        if "model_not_found" in message or "not supported" in message:
            pytest.skip("Requested OpenAI model unavailable")
        raise

    assert generation.candidates, "Expected non-empty candidate list"

    # Limit ranking workload for the integration test
    candidate_subset = generation.candidates[:40]

    try:
        payload = rank_candidates(
            preferences,
            candidate_subset,
            taste_profile=generation.taste_profile,
            llm_client=llm,
            spotify_client=spotify,
            cache_client=cache_client,
        )
    except RuntimeError as error:
        message = str(error).lower()
        if "insufficient_quota" in message or "quota" in message:
            pytest.skip("OpenAI quota exceeded")
        if "model_not_found" in message or "not supported" in message:
            pytest.skip("Requested OpenAI model unavailable")
        raise

    assert payload.recommendations, "Expected recommendations from live ranking"
    assert payload.metadata["taste_profile"]["genres"]
