import React, { useState, useEffect } from 'react'
import './App.css'
import RatingButtons from './components/RatingButtons'
import Recommendations from './components/Recommendations'

function App() {
  const [currentArtist, setCurrentArtist] = useState('')
  const [ratings, setRatings] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [showRecommendations, setShowRecommendations] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const [artists, setArtists] = useState([])
  const [artistIndex, setArtistIndex] = useState(0)
  const [isLoadingArtists, setIsLoadingArtists] = useState(true)

  // Fetch artists from backend
  useEffect(() => {
    const fetchArtists = async () => {
      try {
        setIsLoadingArtists(true)
        // Fetch from popular_artist.py backend endpoint
        const response = await fetch('/api/popular-artists')
        if (!response.ok) {
          throw new Error('Failed to fetch artists')
        }
        const data = await response.json()
        // Convert the ARTISTS set/list to array format
        setArtists(data.artists || [])
      } catch (error) {
        console.error('Error fetching artists:', error)
        // Fallback to empty array if API fails
        setArtists([])
      } finally {
        setIsLoadingArtists(false)
      }
    }

    fetchArtists()
  }, [])

  useEffect(() => {
    if (artists[artistIndex]) {
      setCurrentArtist(artists[artistIndex])
    }
  }, [artists, artistIndex])

  const handleRating = async (rating) => {
    const newRating = {
      artist: currentArtist,
      rating: rating,
      timestamp: new Date().toISOString()
    }

    setRatings(prev => [...prev, newRating])
    setIsLoading(true)

    try {
      // Send rating to backend
      const response = await fetch('/api/rate-artist', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newRating)
      })

      if (!response.ok) {
        throw new Error('Failed to submit rating')
      }

      // Move to next artist
      const nextIndex = artistIndex + 1
      if (nextIndex < artists.length) {
        setArtistIndex(nextIndex)
      } else {
        // After rating all artists, get recommendations
        await fetchRecommendations()
      }
    } catch (error) {
      console.error('Error submitting rating:', error)
      // Still move to next artist even if API call fails
      const nextIndex = artistIndex + 1
      if (nextIndex < artists.length) {
        setArtistIndex(nextIndex)
      } else {
        await fetchRecommendations()
      }
    } finally {
      setIsLoading(false)
    }
  }

  const fetchRecommendations = async () => {
    try {
      const response = await fetch('/api/recommendations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ratings })
      })

      if (!response.ok) {
        throw new Error('Failed to fetch recommendations')
      }

      const data = await response.json()
      setRecommendations(data.recommendations || [])
      setShowRecommendations(true)
    } catch (error) {
      console.error('Error fetching recommendations:', error)
      // Fallback to sample recommendations
      setRecommendations([
        { name: 'Tim Hecker', score: 0.95, reason: 'Similar ambient textures' },
        { name: 'Grouper', score: 0.92, reason: 'Atmospheric soundscapes' },
        { name: 'Stars of the Lid', score: 0.89, reason: 'Drone and ambient' },
        { name: 'William Basinski', score: 0.87, reason: 'Experimental ambient' },
        { name: 'Biosphere', score: 0.85, reason: 'Arctic ambient' }
      ])
      setShowRecommendations(true)
    }
  }

  const resetApp = () => {
    setRatings([])
    setRecommendations([])
    setShowRecommendations(false)
    setArtistIndex(0)
    // Optionally refetch artists for a fresh start
    // fetchArtists()
  }

  // Loading state while fetching artists
  if (isLoadingArtists) {
    return (
      <div className="app">
        <div className="container">
          <h1 className="title">Loading Artists...</h1>
          <p className="subtitle">Fetching music recommendations for you</p>
          <div className="loading-spinner"></div>
        </div>
      </div>
    )
  }

  // No artists available
  if (artists.length === 0) {
    return (
      <div className="app">
        <div className="container">
          <h1 className="title">No Artists Available</h1>
          <p className="subtitle">Unable to load artists from the backend</p>
          <button className="reset-button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (showRecommendations) {
    return (
      <div className="app">
        <div className="container">
          <h1 className="title">Your Music Recommendations</h1>
          <p className="subtitle">Based on your {ratings.length} ratings</p>
          <Recommendations recommendations={recommendations} />
          <button className="reset-button" onClick={resetApp}>
            Start Over
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="container">
        <div className="progress">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${(ratings.length / artists.length) * 100}%` }}
            ></div>
          </div>
          <p className="progress-text">
            {ratings.length} of {artists.length} artists rated
          </p>
        </div>

        <div className="artist-section">
          <h1 className="artist-name">{currentArtist}</h1>
          <p className="artist-subtitle">How do you feel about this artist?</p>
        </div>

        <RatingButtons 
          onRating={handleRating} 
          isLoading={isLoading}
        />

        <div className="stats">
          <p>Love: {ratings.filter(r => r.rating === 'love').length}</p>
          <p>Like: {ratings.filter(r => r.rating === 'like').length}</p>
          <p>Dislike: {ratings.filter(r => r.rating === 'dislike').length}</p>
          <p>Hate: {ratings.filter(r => r.rating === 'hate').length}</p>
        </div>
      </div>
    </div>
  )
}

export default App
