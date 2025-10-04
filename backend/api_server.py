"""Flask API wiring the recommendation backend to the Vite frontend."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests

from cache import InMemoryCache
from candidates_gen import generate_candidates
from filter_candidates import rank_candidates
from popular_artist import get_artists_list, get_artists_count
from services import build_live_clients


app = Flask(__name__)
CORS(app)  # Enable CORS for development

BACKEND_CACHE = InMemoryCache()
CLIENTS = build_live_clients(cache_client=BACKEND_CACHE)
RATING_LOG: List[Dict[str, str]] = []  # non-persistent, useful for debugging


def _bucket_preferences(ratings: List[Dict[str, str]]) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {key: [] for key in ("love", "like", "dislike", "hate")}
    for entry in ratings:
        artist = entry.get("artist", "").strip()
        rating_value = (entry.get("rating", "") or "").lower()
        if artist and rating_value in buckets:
            if artist not in buckets[rating_value]:
                buckets[rating_value].append(artist)

    # Promote likes if the user never selected "love"
    if not buckets["love"] and buckets["like"]:
        buckets["love"] = buckets["like"][:3]

    return buckets


@app.route("/api/popular-artists", methods=["GET"])
def get_popular_artists():
    try:
        artists = get_artists_list()
        return jsonify({
            "artists": artists,
            "count": get_artists_count(),
            "status": "success",
        })
    except Exception as exc:  # pragma: no cover - defensive guard
        return jsonify({"error": str(exc), "status": "error"}), 500


@app.route("/api/rate-artist", methods=["POST"])
def rate_artist():
    try:
        payload = request.get_json(force=True)
        required_fields = {"artist", "rating", "timestamp"}
        if not required_fields.issubset(payload):
            missing = required_fields - set(payload)
            return jsonify({
                "error": f"Missing required fields: {', '.join(sorted(missing))}",
                "status": "error",
            }), 400

        rating_value = payload["rating"].lower()
        if rating_value not in {"love", "like", "dislike", "hate"}:
            return jsonify({
                "error": "rating must be one of love, like, dislike, hate",
                "status": "error",
            }), 400

        RATING_LOG.append(payload)
        return jsonify({"message": "Rating received", "status": "success"})
    except Exception as exc:  # pragma: no cover - defensive guard
        return jsonify({"error": str(exc), "status": "error"}), 500


@app.route("/api/recommendations", methods=["POST"])
def get_recommendations():
    try:
        payload = request.get_json(force=True)
        ratings = payload.get("ratings") or []

        if not ratings:
            return jsonify({
                "error": "At least one rating is required before requesting recommendations.",
                "status": "error",
            }), 400

        preferences = _bucket_preferences(ratings)
        if not preferences["love"]:
            return jsonify({
                "error": "Please rate at least one artist as love or like before requesting recommendations.",
                "status": "error",
            }), 400

        generation = generate_candidates(
            preferences,
            llm_client=CLIENTS["llm_client"],
            spotify_client=CLIENTS["spotify_client"],
            cache_client=CLIENTS["cache_client"],
            enable_llm_query_expansion=False,
        )

        if not generation.candidates:
            return jsonify({
                "recommendations": [],
                "status": "success",
                "metadata": {"notes": ["No suitable candidates were generated"]},
            })

        ranking = rank_candidates(
            preferences,
            generation.candidates,
            taste_profile=generation.taste_profile,
            llm_client=CLIENTS["llm_client"],
            spotify_client=CLIENTS["spotify_client"],
            cache_client=CLIENTS["cache_client"],
        )

        response_payload = {
            "recommendations": [
                {
                    "name": item.candidate.name,
                    "spotify_id": item.candidate.spotify_id,
                    "score": item.aggregate_score,
                    "similarity": item.similarity_score,
                    "penalty": item.penalty_score,
                    "sources": sorted(item.candidate.metadata.get("sources", {item.candidate.source})),
                    "flags": sorted(item.candidate.flags),
                    "rationale": item.rationale,
                }
                for item in ranking.recommendations[:20]
            ],
            "metadata": {
                "taste_profile": ranking.metadata,
                "diagnostics": {
                    "dimension_weights": ranking.diagnostics.dimension_weights,
                    "diversity_score": ranking.diagnostics.diversity_score,
                    "source_coverage": ranking.diagnostics.source_coverage,
                    "total_candidates": ranking.diagnostics.total_candidates,
                    "filtered_candidates": ranking.diagnostics.filtered_candidates,
                    "generation_notes": generation.diagnostics.get("notes", []),
                },
            },
            "status": "success",
        }

        return jsonify(response_payload)

    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response else 502
        return jsonify({
            "error": "Upstream API error while generating recommendations.",
            "details": str(exc),
            "status": "error",
        }), status
    except Exception as exc:  # pragma: no cover - defensive guard
        return jsonify({"error": str(exc), "status": "error"}), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "message": "Algorhythmn API server is running",
        "artists": get_artists_count(),
    })


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    print("Starting Algorhythmn API server...")
    print(f"Available artists: {get_artists_count()}")
    app.run(debug=True, host="0.0.0.0", port=5000)
