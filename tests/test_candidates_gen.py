from backend import cache
from backend import config
from backend import models
from backend.candidates_gen import generate_candidates


class FakeLLMClient:
    def generate_taste_profile(self, preferences):
        return {
            "genres": ["electronic"],
            "scenes": ["berlin"],
            "moods": ["dark"],
            "liked_descriptors": ["glitch", "ambient"],
        }

    def expand_queries(self, taste_profile, base_queries):
        return ["avant electronic"]


class FakeSpotifyClient:
    def __init__(self):
        self.search_data = {
            "underground electronic": [
                {
                    "id": "cand1",
                    "name": "Echo Drift",
                    "popularity": 20,
                    "genres": ["electronic"],
                    "markets": ["US"],
                    "followers": {"total": 32000},
                },
                {
                    "id": "cand2",
                    "name": "Solar Veil",
                    "popularity": 18,
                    "genres": ["ambient"],
                    "followers": {"total": 45000},
                },
                {
                    "id": "cand_low",
                    "name": "Bedroom Experiment",
                    "popularity": 10,
                    "genres": ["lofi"],
                    "followers": {"total": 5000},
                },
            ],
            "experimental berlin": [
                {
                    "id": "cand3",
                    "name": "Disliked Artist",
                    "popularity": 12,
                    "genres": ["techno"],
                    "followers": {"total": 27000},
                }
            ],
            "avant electronic": [
                {
                    "id": "cand4",
                    "name": "Echo Drift",
                    "popularity": 22,
                    "genres": ["idm"],
                    "followers": {"total": 32000},
                }
            ],
            "Artist A Artist B fusion": [
                {
                    "id": "cand5",
                    "name": "Fusion Act",
                    "popularity": 15,
                    "followers": {"total": 38000},
                }
            ],
        }
        self.related_data = {
            "artist_a_id": [
                {
                    "id": "cand6",
                    "name": "Hated Artist",
                    "popularity": 10,
                    "followers": {"total": 36000},
                }
            ]
        }
        self.artists_by_name = {
            "Artist A": {"id": "artist_a_id", "name": "Artist A", "followers": {"total": 90000}},
            "Artist B": {"id": "artist_b_id", "name": "Artist B", "followers": {"total": 85000}},
            "artist a": {"id": "artist_a_id", "name": "Artist A", "followers": {"total": 90000}},
            "artist b": {"id": "artist_b_id", "name": "Artist B", "followers": {"total": 85000}},
        }

    def search_artists(self, query, limit=config.MAX_RESULTS_PER_QUERY):
        return list(self.search_data.get(query, []))

    def get_related_artists(self, artist_id):
        return list(self.related_data.get(artist_id, []))

    def get_artist_by_name(self, name):
        return self.artists_by_name.get(name) or self.artists_by_name.get(name.lower())

    def get_artist(self, artist_id):
        for bucket in self.search_data.values():
            for artist in bucket:
                if artist.get("id") == artist_id:
                    return artist
        for bucket in self.related_data.values():
            for artist in bucket:
                if artist.get("id") == artist_id:
                    return artist
        return None


def test_generate_candidates_deduplicates_and_flags_dislikes():
    preferences = {
        "love": ["Artist A", "Artist B"],
        "like": ["Genre X"],
        "dislike": ["Disliked Artist"],
        "hate": ["Hated Artist"],
    }
    result = generate_candidates(
        preferences,
        llm_client=FakeLLMClient(),
        spotify_client=FakeSpotifyClient(),
        cache_client=cache.InMemoryCache(),
        enable_llm_query_expansion=True,
    )

    names = {candidate.name for candidate in result.candidates}
    assert "Echo Drift" in names  # from search deduped across sources
    assert "Solar Veil" in names
    assert "Disliked Artist" in names
    assert "Hated Artist" in names  # retained for repulsion scoring
    assert "Bedroom Experiment" not in names

    disliked = next(candidate for candidate in result.candidates if candidate.name == "Disliked Artist")
    assert "disliked" in disliked.flags

    hated = next(candidate for candidate in result.candidates if candidate.name == "Hated Artist")
    assert "hated" in hated.flags

    echo = next(candidate for candidate in result.candidates if candidate.name == "Echo Drift")
    assert echo.popularity == 20  # minimum popularity retained after dedup
    assert echo.metadata["sources"] == {"search"}
    assert result.diagnostics["source_counts"]["search"] >= 3
