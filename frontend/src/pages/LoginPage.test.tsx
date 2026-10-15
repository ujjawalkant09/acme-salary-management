import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ME_KEY } from '@/lib/queryClient'
import { ADMIN, mockApi, renderApp } from '@/test/utils'

import LoginPage from './LoginPage'

afterEach(() => vi.unstubAllGlobals())

function show() {
  const view = renderApp(<LoginPage />, { user: null })
  return { ...view, user: userEvent.setup() }
}

describe('Sign in', () => {
  it('signs in with the trimmed email and stores the user', async () => {
    const fetchMock = mockApi({ 'POST /auth/login': ADMIN })
    const { user, client } = show()
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toBeDisabled()

    await user.type(screen.getByLabelText('Work email'), '  priya.sharma@acme.example ')
    expect(button).toBeDisabled() // still needs the password
    await user.type(screen.getByLabelText('Password'), 'secret')
    await user.click(button)

    await vi.waitFor(() => expect(client.getQueryData(ME_KEY)).toEqual(ADMIN))
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init!.body as string)).toEqual({ email: 'priya.sharma@acme.example', password: 'secret' })
  })

  it('a demo account fills its email and moves to the password', async () => {
    mockApi({})
    const { user } = show()
    await user.click(screen.getByRole('button', { name: /HR Viewer/ }))
    expect(screen.getByLabelText('Work email')).toHaveValue('arjun.mehta@acme.example')
    expect(screen.getByLabelText('Password')).toHaveFocus()
  })

  it('says when the email and password do not match', async () => {
    mockApi({ 'POST /auth/login': () => ({ status: 401, body: { error: { code: 'unauthorized', message: 'Wrong email or password.' } } }) })
    const { user } = show()
    await user.type(screen.getByLabelText('Work email'), 'priya.sharma@acme.example')
    await user.type(screen.getByLabelText('Password'), 'wrong{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent("That email and password don't match.")
  })

  it('shows other errors as the server explains them', async () => {
    mockApi({
      'POST /auth/login': () => ({ status: 429, body: { error: { code: 'rate_limited', message: 'Slow down', details: { retry_after: 42 } } } }),
    })
    const { user } = show()
    await user.type(screen.getByLabelText('Work email'), 'priya.sharma@acme.example')
    await user.type(screen.getByLabelText('Password'), 'x{Enter}')
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 42 seconds.')
  })
})
