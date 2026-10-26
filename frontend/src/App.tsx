import { Result, Spin } from 'antd'
import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'

import { useMe } from './api'
import Shell from './components/Shell'
import Dashboard from './pages/Dashboard'
// Daily reports stay in the main bundle: a vessel must be able to file one offline even if it never opened the page.
import Reports from './pages/Reports'
import SignIn from './pages/SignIn'

// Every other page loads when first opened, so signing in does not wait for the map library and every screen.
const Audit = lazy(() => import('./pages/Audit'))
const Certificates = lazy(() => import('./pages/Certificates'))
const ClientPortal = lazy(() => import('./pages/ClientPortal'))
const Contracts = lazy(() => import('./pages/Contracts'))
const Crew = lazy(() => import('./pages/Crew'))
const Invoices = lazy(() => import('./pages/Invoices'))
const Maintenance = lazy(() => import('./pages/Maintenance'))
const Planner = lazy(() => import('./pages/Planner'))
const Readiness = lazy(() => import('./pages/Readiness'))
const Users = lazy(() => import('./pages/Users'))
const VesselDetail = lazy(() => import('./pages/VesselDetail'))
const Vessels = lazy(() => import('./pages/Vessels'))

export default function App() {
  const me = useMe()
  if (me.isPending) return <Spin fullscreen />
  if (me.isError) return <Result status="error" title="The server cannot be reached" subTitle={me.error.message} />
  if (!me.data) return <SignIn />
  if (me.data.role === 'client') return <ClientPortal me={me.data} />
  return (
    <Routes>
      <Route element={<Shell me={me.data} />}>
        <Route index element={<Dashboard me={me.data} />} />
        <Route path="vessels" element={<Vessels />} />
        <Route path="vessels/:vesselId" element={<VesselDetail />} />
        <Route path="certificates" element={<Certificates me={me.data} />} />
        <Route path="readiness" element={<Readiness />} />
        <Route path="maintenance" element={<Maintenance />} />
        <Route path="crew" element={<Crew me={me.data} />} />
        <Route path="planner" element={<Planner />} />
        <Route path="contracts" element={<Contracts me={me.data} />} />
        <Route path="reports" element={<Reports me={me.data} />} />
        <Route path="invoices" element={<Invoices me={me.data} />} />
        <Route path="audit" element={<Audit />} />
        <Route path="users" element={<Users me={me.data} />} />
        <Route path="*" element={<Result status="404" title="Page not found" />} />
      </Route>
    </Routes>
  )
}
