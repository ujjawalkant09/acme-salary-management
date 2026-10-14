import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ADMIN, mockApi, renderApp, VIEWER } from '@/test/utils'

import { AppShell } from './AppShell'

afterEach(() => vi.unstubAllGlobals())

describe('App shell', () => {
  it('shows who is signed in and lets HR Admins add employees', () => {
    mockApi({})
    renderApp(<AppShell>page</AppShell>, { user: ADMIN })
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument()
    expect(screen.getByText('HR Admin')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add employee' })).toBeInTheDocument()
  })

  it('hides Add employee from HR Viewers', () => {
    mockApi({})
    renderApp(<AppShell>page</AppShell>, { user: VIEWER })
    expect(screen.getByText('HR Viewer')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add employee' })).toBeNull()
  })

  it('sends a header search to People and focuses search with /', async () => {
    mockApi({})
    const user = userEvent.setup()
    renderApp(<AppShell>page</AppShell>)
    await user.keyboard('/')
    expect(screen.getByLabelText('Search people')).toHaveFocus()
    await user.keyboard('asha{Enter}')
    expect(screen.getByTestId('location')).toHaveTextContent('/people?q=asha')
  })
})
