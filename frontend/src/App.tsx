import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'

import { AppShell } from '@/components/AppShell'
import { PageLoading } from '@/components/states'
import { useMe, UserContext } from '@/lib/auth'
import LoginPage from '@/pages/LoginPage'

// Each page is its own chunk; the sign-in page is in the main bundle because it shows first.
const HomePage = lazy(() => import('@/pages/HomePage'))
const PeoplePage = lazy(() => import('@/pages/PeoplePage'))
const EmployeePage = lazy(() => import('@/pages/EmployeePage'))
const InsightsPage = lazy(() => import('@/pages/InsightsPage'))
const ImportsPage = lazy(() => import('@/pages/ImportsPage'))
const ChangesPage = lazy(() => import('@/pages/ChangesPage'))
const UsersPage = lazy(() => import('@/pages/UsersPage'))

export default function App() {
  const { data: user, isPending, isError, refetch } = useMe()

  if (isPending) return <PageLoading />
  if (isError) {
    return (
      <div className="grid min-h-full place-items-center p-6 text-center">
        <div>
          <p className="mb-3">Can't reach the server.</p>
          <button className="text-primary underline" onClick={() => refetch()}>
            Try again
          </button>
        </div>
      </div>
    )
  }
  if (!user) return <LoginPage />

  return (
    <UserContext value={user}>
      <AppShell>
        <Suspense fallback={<PageLoading />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/people" element={<PeoplePage />} />
            <Route path="/people/:id" element={<EmployeePage />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/imports" element={<ImportsPage />} />
            <Route path="/changes" element={<ChangesPage />} />
            {user.role === 'hr_admin' && <Route path="/users" element={<UsersPage />} />}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AppShell>
    </UserContext>
  )
}
