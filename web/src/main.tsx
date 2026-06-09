import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

const rootElement = document.getElementById('root')
if (!rootElement) {
  console.error('Failed to find root element')
  throw new Error('Root element not found')
}

createRoot(rootElement).render(<StrictMode><App /></StrictMode>)
