"""
Flask API server for the Algorhythmn frontend.
This provides the web API endpoints that the React frontend will consume.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import json
from popular_artist import get_artists_list, get_artists_count

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

@app.route('/api/popular-artists', methods=['GET'])
def get_popular_artists():
    """
    API endpoint to get the list of popular artists.
    
    Returns:
        JSON response with artists list
    """
    try:
        artists = get_artists_list()
        return jsonify({
            'artists': artists,
            'count': get_artists_count(),
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/rate-artist', methods=['POST'])
def rate_artist():
    """
    API endpoint to submit artist ratings.
    
    Expected JSON payload:
    {
        "artist": "Artist Name",
        "rating": "love|like|dislike|hate",
        "timestamp": "2024-01-01T00:00:00Z"
    }
    
    Returns:
        JSON response confirming the rating was received
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['artist', 'rating', 'timestamp']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'error': f'Missing required field: {field}',
                    'status': 'error'
                }), 400
        
        # Validate rating value
        valid_ratings = ['love', 'like', 'dislike', 'hate']
        if data['rating'] not in valid_ratings:
            return jsonify({
                'error': f'Invalid rating. Must be one of: {valid_ratings}',
                'status': 'error'
            }), 400
        
        # Here you would typically save the rating to a database
        # For now, we'll just log it
        print(f"Rating received: {data['artist']} - {data['rating']} at {data['timestamp']}")
        
        return jsonify({
            'message': 'Rating received successfully',
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    """
    API endpoint to get music recommendations based on user ratings.
    
    Expected JSON payload:
    {
        "ratings": [
            {"artist": "Artist Name", "rating": "love", "timestamp": "..."},
            ...
        ]
    }
    
    Returns:
        JSON response with recommended artists
    """
    try:
        data = request.get_json()
        
        if 'ratings' not in data:
            return jsonify({
                'error': 'Missing required field: ratings',
                'status': 'error'
            }), 400
        
        ratings = data['ratings']
        
        # Here you would call your existing recommendation logic
        # For now, we'll return sample recommendations
        sample_recommendations = [
            {
                'name': 'Tim Hecker',
                'score': 0.95,
                'reason': 'Similar ambient textures'
            },
            {
                'name': 'Grouper',
                'score': 0.92,
                'reason': 'Atmospheric soundscapes'
            },
            {
                'name': 'Stars of the Lid',
                'score': 0.89,
                'reason': 'Drone and ambient'
            }
        ]
        
        return jsonify({
            'recommendations': sample_recommendations,
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.
    
    Returns:
        JSON response indicating server status
    """
    return jsonify({
        'status': 'healthy',
        'message': 'Algorhythmn API server is running'
    })

if __name__ == '__main__':
    print("Starting Algorhythmn API server...")
    print(f"Available artists: {get_artists_count()}")
    app.run(debug=True, host='0.0.0.0', port=5000)
