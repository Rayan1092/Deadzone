import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'

// Each route is its own chunk, so phones never download three.js.
const BigScreen = lazy(() => import('./BigScreen'))
const PhoneApp = lazy(() => import('./phone/PhoneApp'))

const Root = location.pathname.startsWith('/phone') ? PhoneApp : BigScreen
ReactDOM.createRoot(document.getElementById('root')).render(
  <Suspense fallback={null}><Root /></Suspense>,
)
