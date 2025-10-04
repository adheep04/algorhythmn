Implementation Plan
===================

Strategy Assessment
- Candidate Generation: Multi-pronged search + popularity filter remains core; start with deterministic query templates to guarantee coverage, layering LLM-assisted expansion as a later enhancement.
- Filtering & Ranking: Adopt hybrid embeddings that pair Spotify audio features for objective axes with high-capacity LLM judgments for subjective ones, while retaining dislike/hate overlaps for repulsion scoring instead of discarding them.
- Operational Considerations: Centralize configuration, keep a lightweight in-memory cache for API/LLM responses, and log provenance plus diversity metrics so debugging and tuning stay fast.

Implementation Outline
1. Shared foundation: add `config.py` with thresholds (e.g., POPULARITY_THRESHOLD=35, TARGET_CANDIDATES=150, DIVERSITY_WEIGHT=0.3), create `models.py` dataclasses (`TasteProfile`, `ArtistCandidate`, `ArtistEmbedding`), and expose an in-memory cache helper (`cache.py`) for reuse.
2. Taste profiling: validate preference lists, call a high-tier reasoning model (e.g., Claude 3.5 Sonnet or OpenAI o1) with guardrails to produce structured characteristics, and store the result in cache keyed by a stable hash of preferences.
3. Query generation: derive 20 baseline queries by combining taste-profile genres/scenes with modifiers such as `underground`, `experimental`, and `new`; dedupe, cap per config, and optionally enable LLM-augmented variants behind a feature flag.
4. Spotify client integration: implement thin wrappers for search, related artists, and cross-pollination queries that honor rate limits, memoize responses, and normalize artist payloads.
5. Candidate aggregation: execute multi-source retrieval (search, related, cross), annotate each candidate with source metadata, enforce popularity/market filters early, and record fetch diagnostics for observability.
6. Candidate normalization: merge duplicates by normalized name, consolidate metadata, and flag overlaps with user dislikes/hates instead of removing them so they can drive repulsion during scoring.
7. Candidate enrichment: fetch Spotify audio features to populate energy, danceability, valence, acousticness, and instrumentalness; have the LLM supply experimental, complexity, and harshness scores; cache results and provide heuristics when enrichment fails.
8. Preference embedding weights: ensure loved-artist embeddings exist (pre-compute and cache), compute per-dimension variance, derive inverse-variance weights normalized to sum to one, and persist for reuse within the session.
9. Scoring pipeline: compute weighted distances to loved and hated artists, apply penalties for dislike/hate flags, and emit similarity, penalty, aggregate scores, plus short textual rationales.
10. Diversity selection: run MMR-style selection using the configured diversity weight, guarantee minimum coverage across retrieval sources, and suppress any candidate explicitly tagged as dislike/hate from the final recommendation slate.
11. Output assembly: package top recommendations (default 30), the remaining ranked backlog, dimension weights, source coverage, and diagnostics (filter counts, diversity score) into a structured payload for the frontend.
12. Observability & fallbacks: add logging hooks for cache hits, API usage, and scoring outcomes; implement fallbacks that skip LLM enrichment when unavailable and rely on Spotify features only.

Module Responsibilities
- `backend/candidates_gen.py`: implement Steps 2-6 plus caching hooks and expose `generate_candidates(preferences, llm_client, spotify_client, cache)`.
- `backend/filter_candidates.py`: implement Steps 7-12, covering embedding computation, weighting, scoring, diversity selection, and payload assembly via `rank_candidates(preferences, candidate_pool, llm_client, spotify_client, cache)`.

Validation Plan
- Unit-test deterministic query generation, deduplication/flagging logic, weight calculation, and scoring math with controlled fixtures.
- Create integration tests with mocked LLM/Spotify clients and seeded cache to verify the end-to-end flow from preferences to ranked output.
- Add assertions or snapshot tests for metadata logging (source coverage, diversity score) and fallback behavior when enrichment calls fail.

Decisions & Defaults
- LLM usage: rely on high-capability non-GPT-3.5/4 models (e.g., Claude 3.5 Sonnet or OpenAI o1) for taste profiling and subjective embeddings; fall back to stored heuristics when unavailable.
- Embedding mix: Spotify audio features supply five objective dimensions; the LLM provides the three subjective axes to reduce latency and cost.
- Caching: an in-memory dictionary cache suffices for hackathon scope yet can be swapped for persistent storage later.
- Frontend payload: expose `recommendations`, `metadata` (taste profile, dimension weights, source coverage), and `diagnostics` (totals, filtered counts, diversity score) to support UI presentation.

Open Questions
- Do we need additional non-Spotify sources (e.g., Bandcamp, SoundCloud) to boost coverage for certain niches?
- Should cache entries persist across sessions (file/Redis) if the prototype expands to multi-user usage?
- What telemetry granularity does the team expect for monitoring API consumption and recommendation outcomes?

Delivery Accelerators
- Pre-compute embeddings for hardcoded popular artists to avoid repeated LLM calls.
- Batch Spotify requests and short-circuit enrichment for artists above the popularity threshold.
- Provide a fallback scoring mode that leans solely on Spotify features when the LLM budget is exhausted.
