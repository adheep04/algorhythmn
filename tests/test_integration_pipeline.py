from backend import cache
from backend.candidates_gen import generate_candidates
from backend.filter_candidates import rank_candidates


class IntegratedLLMClient:
    def __init__(self):
        self.query_expansions_called = 0

    def generate_taste_profile(self, preferences):
        return {
            "genres": ["electronic"],
            "scenes": ["berlin"],
            "moods": ["dark"],
            "liked_descriptors": ["glitch"],
        }

    def expand_queries(self, taste_profile, base_queries):
        self.query_expansions_called += 1
        return ["avant electronic"]

    def score_subjective_dimensions(self, artist_name, context):
        scores = {
            "Echo Drift": {"experimental": 0.85, "complexity": 0.7, "harshness": 0.3},
            "Solar Veil": {"experimental": 0.65, "complexity": 0.5, "harshness": 0.2},
            "Disliked Artist": {"experimental": 0.6, "complexity": 0.4, "harshness": 0.5},
            "Hated Artist": {"experimental": 0.2, "complexity": 0.3, "harshness": 0.1},
            "Fusion Act": {"experimental": 0.7, "complexity": 0.6, "harshness": 0.4},
            "Artist A": {"experimental": 0.9, "complexity": 0.8, "harshness": 0.2},
            "Artist B": {"experimental": 0.4, "complexity": 0.3, "harshness": 0.7},
        }
        return dict(scores.get(artist_name, {}))


class IntegratedSpotifyClient:
    def __init__(self):
        self.search_data = {
            "underground electronic": [
                {
                    "id": "cand1",
                    "name": "Echo Drift",
                    "popularity": 22,
                    "genres": ["electronic"],
                    "followers": {"total": 34000},
                },
                {
                    "id": "cand2",
                    "name": "Solar Veil",
                    "popularity": 18,
                    "genres": ["ambient"],
                    "followers": {"total": 42000},
                },
            ],
            "experimental berlin": [
                {
                    "id": "cand3",
                    "name": "Disliked Artist",
                    "popularity": 15,
                    "genres": ["techno"],
                    "followers": {"total": 29000},
                }
            ],
            "avant electronic": [
                {
                    "id": "cand1",
                    "name": "Echo Drift",
                    "popularity": 21,
                    "genres": ["idm"],
                    "followers": {"total": 34000},
                }
            ],
            "Artist A Artist B fusion": [
                {
                    "id": "cand5",
                    "name": "Fusion Act",
                    "popularity": 16,
                    "followers": {"total": 36000},
                }
            ],
        }
        self.related_data = {
            "artist_a_id": [
                {
                    "id": "cand6",
                    "name": "Hated Artist",
                    "popularity": 12,
                    "followers": {"total": 28000},
                }
            ]
        }
        self.artist_lookup = {
            "Artist A": {"id": "artist_a_id", "name": "Artist A", "followers": {"total": 110000}},
            "Artist B": {"id": "artist_b_id", "name": "Artist B", "followers": {"total": 95000}},
        }
        self.audio_features = {
            "cand1": {
                "energy": 0.8,
                "danceability": 0.7,
                "valence": 0.4,
                "acousticness": 0.1,
                "instrumentalness": 0.85,
            },
            "cand2": {
                "energy": 0.6,
                "danceability": 0.5,
                "valence": 0.5,
                "acousticness": 0.2,
                "instrumentalness": 0.7,
            },
            "cand3": {
                "energy": 0.4,
                "danceability": 0.35,
                "valence": 0.3,
                "acousticness": 0.6,
                "instrumentalness": 0.6,
            },
            "cand5": {
                "energy": 0.7,
                "danceability": 0.6,
                "valence": 0.45,
                "acousticness": 0.25,
                "instrumentalness": 0.5,
            },
            "cand6": {
                "energy": 0.2,
                "danceability": 0.15,
                "valence": 0.1,
                "acousticness": 0.8,
                "instrumentalness": 0.4,
            },
            "artist_a_id": {
                "energy": 0.85,
                "danceability": 0.75,
                "valence": 0.5,
                "acousticness": 0.05,
                "instrumentalness": 0.9,
            },
            "artist_b_id": {
                "energy": 0.5,
                "danceability": 0.45,
                "valence": 0.35,
                "acousticness": 0.3,
                "instrumentalness": 0.6,
            },
        }

    def search_artists(self, query, limit):
        return list(self.search_data.get(query, []))

    def get_related_artists(self, artist_id):
        return list(self.related_data.get(artist_id, []))

    def get_artist_by_name(self, name):
        return self.artist_lookup.get(name)

    def get_artist_audio_features(self, artist_id):
        return dict(self.audio_features.get(artist_id, {}))

    def get_artist(self, artist_id):
        for bucket in self.search_data.values():
            for artist in bucket:
                if artist.get("id") == artist_id:
                    return artist
        for bucket in self.related_data.values():
            for artist in bucket:
                if artist.get("id") == artist_id:
                    return artist
        for artist in self.artist_lookup.values():
            if artist.get("id") == artist_id:
                return artist
        return None


def test_end_to_end_candidate_generation_and_ranking():
    preferences = {
        "love": ["Artist A", "Artist B"],
        "dislike": ["Disliked Artist"],
        "hate": ["Hated Artist"],
    }
    cache_client = cache.InMemoryCache()
    llm_client = IntegratedLLMClient()
    spotify_client = IntegratedSpotifyClient()

    generation = generate_candidates(
        preferences,
        llm_client=llm_client,
        spotify_client=spotify_client,
        cache_client=cache_client,
        enable_llm_query_expansion=True,
    )

    assert generation.candidates
    assert any(candidate.name == "Hated Artist" for candidate in generation.candidates)

    payload = rank_candidates(
        preferences,
        generation.candidates,
        taste_profile=generation.taste_profile,
        llm_client=llm_client,
        spotify_client=spotify_client,
        cache_client=cache_client,
    )

    rec_names = [item.candidate.name for item in payload.recommendations]
    assert rec_names[0] == "Echo Drift"
    assert "Hated Artist" not in rec_names
    assert payload.diagnostics.total_candidates == len(generation.candidates)
    assert payload.metadata["taste_profile"]["genres"] == ["electronic"]
