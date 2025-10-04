import pytest

from backend import cache
from backend import models
from backend.filter_candidates import rank_candidates


class FakeRankingLLM:
    def __init__(self):
        self.subjective_scores = {
            "Echo Drift": {"experimental": 0.8, "complexity": 0.7, "harshness": 0.3},
            "Disliked Artist": {"experimental": 0.6, "complexity": 0.4, "harshness": 0.5},
            "Hated Artist": {"experimental": 0.2, "complexity": 0.3, "harshness": 0.1},
            "Loved Ref": {"experimental": 0.9, "complexity": 0.8, "harshness": 0.2},
            "Hated Ref": {"experimental": 0.1, "complexity": 0.2, "harshness": 0.9},
        }

    def score_subjective_dimensions(self, artist_name, context):
        return dict(self.subjective_scores.get(artist_name, {}))


class FakeRankingSpotify:
    def __init__(self):
        self.audio_features = {
            "cand1": {
                "energy": 0.7,
                "danceability": 0.65,
                "valence": 0.4,
                "acousticness": 0.1,
                "instrumentalness": 0.8,
            },
            "cand2": {
                "energy": 0.5,
                "danceability": 0.4,
                "valence": 0.6,
                "acousticness": 0.3,
                "instrumentalness": 0.7,
            },
            "cand3": {
                "energy": 0.3,
                "danceability": 0.2,
                "valence": 0.2,
                "acousticness": 0.7,
                "instrumentalness": 0.4,
            },
            "loved_id": {
                "energy": 0.8,
                "danceability": 0.7,
                "valence": 0.5,
                "acousticness": 0.05,
                "instrumentalness": 0.9,
            },
            "hated_id": {
                "energy": 0.2,
                "danceability": 0.1,
                "valence": 0.1,
                "acousticness": 0.9,
                "instrumentalness": 0.3,
            },
        }
        self.artist_lookup = {
            "Loved Ref": {"id": "loved_id", "name": "Loved Ref", "followers": {"total": 120000}},
            "Hated Ref": {"id": "hated_id", "name": "Hated Ref", "followers": {"total": 50000}},
        }

    def get_artist_audio_features(self, artist_id):
        return dict(self.audio_features.get(artist_id, {}))

    def get_artist_by_name(self, name):
        return self.artist_lookup.get(name)

    def get_artist(self, artist_id):
        for artist in self.artist_lookup.values():
            if artist.get("id") == artist_id:
                return artist
        return None


def _build_candidate(candidate_id, name, source):
    candidate = models.ArtistCandidate(
        spotify_id=candidate_id,
        name=name,
        popularity=20,
        source=source,
        source_query=source,
        followers=40000,
    )
    candidate.metadata["sources"] = {source}
    return candidate


def test_rank_candidates_excludes_hated_and_weighs_preferences():
    candidates = [
        _build_candidate("cand1", "Echo Drift", "search"),
        _build_candidate("cand2", "Disliked Artist", "related"),
        _build_candidate("cand3", "Hated Artist", "search"),
    ]
    candidates[1].tag("disliked")
    candidates[2].tag("hated")

    taste_profile = models.TasteProfile(
        genres=["electronic"],
        scenes=["berlin"],
        moods=["dark"],
        liked_descriptors=["experimental"],
        avoided_descriptors=["acoustic"],
        raw={"from": "test"},
    )

    payload = rank_candidates(
        preferences={
            "love": ["Loved Ref"],
            "hate": ["Hated Ref"],
        },
        candidate_pool=candidates,
        taste_profile=taste_profile,
        llm_client=FakeRankingLLM(),
        spotify_client=FakeRankingSpotify(),
        cache_client=cache.InMemoryCache(),
    )

    assert payload.recommendations
    names = [item.candidate.name for item in payload.recommendations]
    assert "Hated Artist" not in names
    assert names[0] == "Echo Drift"

    # dimension weights sum to 1
    total_weight = sum(payload.diagnostics.dimension_weights.values())
    assert pytest.approx(total_weight, rel=1e-3) == 1.0

    disliked_entry = next(
        item for item in payload.recommendations if item.candidate.name == "Disliked Artist"
    )
    assert disliked_entry.penalty_score > 0.0
