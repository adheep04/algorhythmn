# Algorhythmn Frontend

A modern React frontend for the Algorhythmn music recommendation app.

## Features

- Clean, modern UI with gradient backgrounds and glassmorphism effects
- Artist rating system with four options: Love, Like, Dislike, Hate
- Progress tracking (shows progress through 20 artists)
- Recommendations display after rating 15-20 artists
- Responsive design that works on mobile and desktop
- Real-time statistics showing rating distribution

## Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Start the development server:
```bash
npm run dev
```

3. Open your browser to `http://localhost:3000`

## Building for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## Integration with Backend

The frontend is designed to work with your existing backend. To integrate:

1. Update the API calls in `App.jsx` to point to your backend endpoints
2. Replace the sample artists array with data from your backend
3. Update the recommendations API call to use your actual recommendation endpoint

## File Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── RatingButtons.jsx    # Rating button component
│   │   └── Recommendations.jsx  # Recommendations display
│   ├── App.jsx                  # Main application component
│   ├── App.css                  # Main styles
│   ├── index.css                # Global styles
│   └── main.jsx                 # Entry point
├── index.html                   # HTML template
├── package.json                 # Dependencies
├── vite.config.js              # Vite configuration
└── README.md                   # This file
```

## Customization

- Colors and gradients can be modified in `App.css`
- The number of artists to rate can be changed in `App.jsx` (currently set to 20)
- Button styles and animations can be customized in the CSS files
- The sample artists list can be replaced with your own data
