import React from 'react'
import { createRoot } from 'react-dom/client'
import SimViewer from './SimViewer.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SimViewer />
  </React.StrictMode>,
)
