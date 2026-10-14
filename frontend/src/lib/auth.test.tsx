import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from '@/App'
import { ME_KEY } from '@/lib/queryClient'
import { mockApi, renderApp } from '@/test/utils'

afterEach(() => vi.unstubAllGlobals())

describe('signing out', () => {
  it('shows the sign-in page and forgets the cached data', async () => {
    mockApi({ 'POST /auth/logout': { status: 204 } })
    const user = userEvent.setup()
    const { client } = renderApp(<App />)
    client.setQueryData(['employees', ''], { items: [] })

    await user.click(screen.getByRole('button', { name: /Priya Sharma/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(client.getQueryData(ME_KEY)).toBeNull()
    expect(client.getQueryData(['employees', ''])).toBeUndefined()
  })
})
