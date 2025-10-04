"""Backend configuration constants for recommendation pipeline."""
from __future__ import annotations

# Popularity and selection thresholds
POPULARITY_THRESHOLD: int = 35
TARGET_CANDIDATES: int = 100
TARGET_RECOMMENDATIONS: int = 30
MAX_QUERY_COUNT: int = 40
MAX_RESULTS_PER_QUERY: int = 50

# Diversity and scoring
DIVERSITY_WEIGHT: float = 0.3
MIN_SOURCE_COVERAGE: int = 5  # minimum count per retrieval source when possible

# Audience thresholds
MIN_FOLLOWERS_THRESHOLD: int = 15_000

# Embedding dimension schema (0.0 - 1.0 scale)
DIMENSIONS = [
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "instrumentalness",
    "experimental",
    "complexity",
    "harshness",
]

SPOTIFY_OBJECTIVE_DIMENSIONS = [
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "instrumentalness",
]

SUBJECTIVE_DIMENSIONS = [dim for dim in DIMENSIONS if dim not in SPOTIFY_OBJECTIVE_DIMENSIONS]

# Mapping from dimensions to Spotify audio feature keys and optional transforms
SPOTIFY_AUDIO_FEATURE_MAP = {
    "energy": ("energy", None),
    "danceability": ("danceability", None),
    "valence": ("valence", None),
    "acousticness": ("acousticness", None),
    "instrumentalness": ("instrumentalness", None),
}

# Cache namespaces
CACHE_NAMESPACES = {
    "taste_profile": "taste_profile",
    "search_results": "search_results",
    "artist_details": "artist_details",
    "embeddings": "embeddings",
    "audio_features": "audio_features",
}

# Misc operational constants
CACHE_DEFAULT_TTL_SECONDS: int = 60 * 60  # one hour
LLM_FEATURE_FLAG_KEY = "llm_query_expansion"
