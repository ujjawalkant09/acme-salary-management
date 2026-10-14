import { describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

import { toast } from 'sonner'

import { ApiError } from './api'
import { createQueryClient, ME_KEY } from './queryClient'

const fail = (error: Error) => () => Promise.reject(error)

describe('query client', () => {
  it('signs the person out in the UI when the session has expired', async () => {
    const client = createQueryClient()
    client.setQueryData(ME_KEY, { id: 1 })
    await client.fetchQuery({ queryKey: ['x'], queryFn: fail(new ApiError(401, 'unauthorized', 'Please sign in.')) }).catch(() => {})
    expect(client.getQueryData(ME_KEY)).toBeNull()
  })

  it('toasts failed changes, except field errors which the form shows', async () => {
    const client = createQueryClient()
    const run = (error: Error) => client.getMutationCache().build(client, { mutationFn: fail(error) }).execute(undefined).catch(() => {})
    await run(new ApiError(422, 'invalid', 'Some fields are not valid.'))
    expect(toast.error).not.toHaveBeenCalled()
    await run(new ApiError(409, 'version_conflict', 'This employee was changed by someone else. Reload to see the latest.'))
    expect(toast.error).toHaveBeenCalledWith('This employee was changed by someone else. Reload to see the latest.')
  })

  it('does not retry client errors', async () => {
    const client = createQueryClient()
    const queryFn = vi.fn(fail(new ApiError(404, 'not_found', 'Not found.')))
    await client.fetchQuery({ queryKey: ['y'], queryFn }).catch(() => {})
    expect(queryFn).toHaveBeenCalledTimes(1)
  })
})
