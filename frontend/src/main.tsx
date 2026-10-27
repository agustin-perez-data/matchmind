import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ClubRoom } from './components/ClubRoom'
import { SignIn } from './components/SignIn'

// The club area and its door are their own pages; every other path is the demo, untouched.
const path = location.pathname.replace(/\/+$/, '')
const page = path === '/club' ? <div className="stage flex min-h-full flex-col"><ClubRoom /></div>
  : path === '/signin' ? <div className="stage flex min-h-full flex-col"><SignIn /></div>
    : <App />

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {page}
  </StrictMode>,
)
