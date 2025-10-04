import React from 'react'

const Recommendations = ({ recommendations }) => {
  return (
    <div className="recommendations">
      <div className="recommendations-grid">
        {recommendations.map((rec, index) => (
          <div key={index} className="recommendation-card">
            <div className="recommendation-header">
              <h3 className="recommendation-name">{rec.name}</h3>
              <div className="recommendation-score">
                {Math.round(rec.score * 100)}% match
              </div>
            </div>
            <p className="recommendation-reason">{rec.reason}</p>
            <div className="recommendation-bar">
              <div 
                className="recommendation-fill"
                style={{ width: `${rec.score * 100}%` }}
              ></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default Recommendations
