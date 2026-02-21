/**
 * FORESIGHT Dashboard — Root App Component
 *
 * React Router setup with all routes accessible without authentication.
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Dashboard } from '@/pages/Dashboard'
import { Assets } from '@/pages/Assets'
import { Alerts } from '@/pages/Alerts'
import { Trends } from '@/pages/Trends'
import { Predictions } from '@/pages/Predictions'
import { CostAvoidance } from '@/pages/CostAvoidance'
import { Rules } from '@/pages/Rules'
import { Settings } from '@/pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
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
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
