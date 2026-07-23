import React from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter-tight'
import '@fontsource-variable/geist-mono'
import SimViewer from './SimViewer.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SimViewer />
  </React.StrictMode>,
)
