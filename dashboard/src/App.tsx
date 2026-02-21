/**
 * FORESIGHT Dashboard — Root App Component
 *
 * Sets up React Router with:
 *  - Public route: /login
 *  - Protected routes: everything under AppShell
 *  - Redirect unauthenticated users to /login
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Login } from '@/pages/Login'
import { Dashboard } from '@/pages/Dashboard'
import { Assets } from '@/pages/Assets'
import { Alerts } from '@/pages/Alerts'
import { Trends } from '@/pages/Trends'
import { Predictions } from '@/pages/Predictions'
import { CostAvoidance } from '@/pages/CostAvoidance'
import { Rules } from '@/pages/Rules'
import { Settings } from '@/pages/Settings'
import { useAuthStore } from '@/store/auth'

/** Redirects unauthenticated users to /login */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />

        {/* Protected — wrapped in AppShell (sidebar + topbar) */}
        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"   element={<Dashboard />} />
          <Route path="/assets"      element={<Assets />} />
          <Route path="/alerts"      element={<Alerts />} />
          <Route path="/trends"      element={<Trends />} />
          <Route path="/predictions" element={<Predictions />} />
          <Route path="/cost"        element={<CostAvoidance />} />
          <Route path="/rules"       element={<Rules />} />
          <Route path="/settings"    element={<Settings />} />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
