#!/usr/bin/env python3
"""Run the end-to-end recommendation pipeline against live services."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from backend import cache, env, services
from backend.candidates_gen import generate_candidates
from backend.filter_candidates import rank_candidates

DEFAULT_PREFS = {
    "love": ["Aphex Twin", "Autechre"],
    "like": ["dark ambient"],
    "dislike": ["mainstream pop"],
    "hate": ["Ed Sheeran"],
}


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute the recommendation pipeline using live Spotify and Claude APIs.",
    )
    parser.add_argument(
        "--prefs",
        type=Path,
        help="Path to a JSON file containing {love, like, dislike, hate} arrays.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top recommendations to print (default: 10).",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path to write the full recommendation payload as JSON.",
    )
    parser.add_argument(
        "--no-expansion",
        action="store_true",
        help="Disable LLM query expansion to reduce latency/cost during manual runs.",
    )
    return parser.parse_args(list(argv))


def load_preferences(path: Path | None) -> Dict[str, List[str]]:
    if not path:
        return DEFAULT_PREFS
    data = json.loads(path.read_text())
    prefs: Dict[str, List[str]] = {}
    for bucket in ("love", "like", "dislike", "hate"):
        values = data.get(bucket, [])
        if not isinstance(values, list):
            raise ValueError(f"Preference bucket '{bucket}' must be a list of strings")
        prefs[bucket] = [str(item).strip() for item in values if str(item).strip()]
    return prefs


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    try:
        preferences = load_preferences(args.prefs)
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Failed to load preferences: {exc}", file=sys.stderr)
        return 1

    print("[1/5] Loading environment configuration...", flush=True)
    env.load_env()
    try:
        clients = services.build_live_clients()
    except RuntimeError as exc:
        print(f"Environment not configured correctly: {exc}", file=sys.stderr)
        return 1
    print("[1/5] Environment ready.\n", flush=True)

    try:
        print("[2/5] Generating candidates...", flush=True)
        generation = generate_candidates(
            preferences,
            llm_client=clients["llm_client"],
            spotify_client=clients["spotify_client"],
            cache_client=clients["cache_client"],
            enable_llm_query_expansion=not args.no_expansion,
        )
    except Exception as exc:
        print(f"Candidate generation failed: {exc}", file=sys.stderr)
        return 1

    candidates = generation.candidates
    trimmed_count = generation.diagnostics.get("trimmed_count", 0)
    print(
        f"[2/5] Generated {len(candidates)} candidates from sources "
        f"{generation.diagnostics.get('source_counts', {})}"
        + (f" (trimmed {trimmed_count})" if trimmed_count else "")
        + ".\n",
        flush=True,
    )

    try:
        print("[3/5] Ranking candidates...", flush=True)
        payload = rank_candidates(
            preferences,
            candidates,
            taste_profile=generation.taste_profile,
            llm_client=clients["llm_client"],
            spotify_client=clients["spotify_client"],
            cache_client=clients["cache_client"],
        )
    except Exception as exc:
        print(f"Ranking failed: {exc}", file=sys.stderr)
        return 1

    print("[3/5] Ranking complete.\n", flush=True)

    print("[4/5] Top recommendations:")
    for item in payload.recommendations[: args.top]:
        candidate = item.candidate
        flags = ",".join(sorted(candidate.flags)) or "none"
        sources = ",".join(sorted(candidate.metadata.get("sources", {candidate.source})))
        print(
            f" - {candidate.name:25s} score={item.aggregate_score:6.3f} "
            f"sim={item.similarity_score:6.3f} penalty={item.penalty_score:6.3f} "
            f"flags={flags} sources={sources}"
        )

    diagnostics = payload.diagnostics
    print(
        "\n[4/5] Diagnostics: "
        f"weights={json.dumps(diagnostics.dimension_weights, sort_keys=True)} "
        f"diversity={diagnostics.diversity_score:.3f} "
        f"total_candidates={diagnostics.total_candidates}"
    )

    if args.json:
        print(f"\n[5/5] Writing detailed output to {args.json}...", flush=True)
        args.json.write_text(
            json.dumps(
                {
                    "recommendations": [
                        {
                            "name": item.candidate.name,
                            "spotify_id": item.candidate.spotify_id,
                            "aggregate_score": item.aggregate_score,
                            "similarity_score": item.similarity_score,
                            "penalty_score": item.penalty_score,
                            "flags": sorted(item.candidate.flags),
                            "sources": sorted(item.candidate.metadata.get("sources", {item.candidate.source})),
                        }
                        for item in payload.recommendations
                    ],
                    "backlog_count": len(payload.backlog),
                    "metadata": payload.metadata,
                    "diagnostics": {
                        "dimension_weights": diagnostics.dimension_weights,
                        "diversity_score": diagnostics.diversity_score,
                        "source_coverage": diagnostics.source_coverage,
                        "total_candidates": diagnostics.total_candidates,
                        "filtered_candidates": diagnostics.filtered_candidates,
                    },
                },
                indent=2,
            )
        )

    print("\n[✔] Completed run.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
