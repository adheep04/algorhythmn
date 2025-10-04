import React from 'react'

const RatingButtons = ({ onRating, isLoading }) => {
  const ratings = [
    { key: 'hate', label: 'Hate', emoji: '💔', color: '#ef4444' },
    { key: 'dislike', label: 'Dislike', emoji: '👎', color: '#f97316' },
    { key: 'like', label: 'Like', emoji: '👍', color: '#22c55e' },
    { key: 'love', label: 'Love', emoji: '❤️', color: '#ec4899' }
  ]

  return (
    <div className="rating-buttons">
      {ratings.map(({ key, label, emoji, color }) => (
        <button
          key={key}
          className={`rating-button rating-${key}`}
          onClick={() => onRating(key)}
          disabled={isLoading}
          style={{ '--button-color': color }}
        >
          <span className="rating-emoji">{emoji}</span>
          <span className="rating-label">{label}</span>
        </button>
      ))}
    </div>
  )
}

export default RatingButtons
