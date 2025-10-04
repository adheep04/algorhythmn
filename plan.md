Stage 1: Candidate Generation (100-150 underground artists)
Input
You have user preferences as 4 lists of artist names (love/like/dislike/hate) from your hardcoded popular artists.
Process
Step 1: Taste Profile Extraction
Take the preference lists and send them to an LLM with a prompt that extracts the pattern not specific artists. The LLM returns a structured taste profile that captures what the user is gravitating toward musically. This includes:

Core musical characteristics they like (e.g., "experimental electronic", "harsh textures", "melodic")
What they actively avoid (e.g., "mainstream pop production", "acoustic guitar")
Energy and mood patterns
Era preferences if any

Step 2: Search Query Generation
Use the taste profile to generate 20-30 diverse search queries. The key insight: don't ask the LLM for artist names (it hallucinates), ask it for search strategies. Examples:

Combine liked characteristics: "ethereal harsh electronic"
Opposite of what they hate: if they hate "radio-friendly pop", search "experimental anti-pop"
Geographic scenes: "berlin minimal techno" if they like electronic minimalism
Temporal searches: "2020s bedroom experimental" if they like DIY aesthetics

Step 3: Multi-Source Artist Collection

Spotify Search API: Use each generated query to search Spotify, filter for artists with popularity < 30-40
Related Artists API: For each "loved" artist, get Spotify's related artists, filter for underground only
Cross-pollination: For pairs of loved artists, search for "artist A genre + artist B style" combinations

Step 4: Deduplication
Since the same underground artist might appear from multiple search paths, deduplicate by name (normalized lowercase). This usually gives you 100-150 unique underground artists.
Stage 2: Intelligent Filtering & Ranking
The Embedding Space Approach
Step 1: Create Embedding Schema
Define 8 dimensions that capture music characteristics:

Energy (0=ambient, 1=high-energy)
Electronic vs Organic (0=acoustic, 1=electronic)
Experimental (0=accessible, 1=avant-garde)
Darkness (0=bright, 1=dark)
Complexity (0=simple, 1=complex)
Tempo Feel (0=slow, 1=fast)
Vocal Presence (0=instrumental, 1=vocal-heavy)
Harshness (0=smooth, 1=abrasive)

Step 2: Embed Everything

Your hardcoded popular artists already have embeddings
For each candidate artist, generate embeddings using LLM with context about what dimensions mean
Key: Give the LLM the user's taste profile as context when embedding, so it understands relative positioning

Step 3: Learn User's Preference Space
This is the clever part - not all dimensions matter equally to each user:

Calculate variance across "loved" artists for each dimension
Low variance = user cares about this dimension (they consistently pick artists with similar values)
High variance = user doesn't care about this dimension
Create dimension weights based on inverse variance

Step 4: Similarity Scoring
For each candidate:

Calculate weighted distance to each loved artist (using dimension weights)
Calculate weighted distance to each hated artist
Score = (minimum distance to loved artists) - (minimum distance to hated artists)
Alternative score = sum of similarities to loved - sum of similarities to hated

Step 5: Diversity Optimization
Don't just take top 30 by score (they might all be similar):

Select first artist (highest score)
For next artist, balance score with diversity: final_score = 0.7 * similarity_score + 0.3 * distance_to_already_selected
Repeat until you have 30-50 diverse recommendations

Key Insights That Make This Work

LLM for understanding, APIs for facts: LLM understands taste patterns but doesn't generate artist names. Spotify provides real artists.
Embedding space with learned weights: Not just similarity in raw embedding space, but similarity in the dimensions that matter to THIS user.
Multiple discovery paths: Combining search queries, related artists, and cross-pollination ensures you find artists from different "neighborhoods" of music.
Popularity filter is crucial: Spotify's popularity score (0-100) is your best friend. Under 30 is genuinely underground.
Diversity by design: The MMR-style diversity optimization prevents recommending 30 artists that all sound identical.
