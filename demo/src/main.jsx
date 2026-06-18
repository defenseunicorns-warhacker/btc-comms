import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.jsx'

// No StrictMode: its dev double-invoke would open two SSE streams and could
// double-fire the scripted event sequence. The demo wants one clean timeline.
createRoot(document.getElementById('root')).render(<App />)
