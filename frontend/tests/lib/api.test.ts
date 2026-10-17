import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockApi } from '@tests/support/utils'

import { api, ApiError, errorMessage, toQuery } from '@/lib/api'

afterEach(() => vi.unstubAllGlobals())

function failIfResolved(): never {
  throw new Error('expected the request to fail')
}

describe('api', () => {
  it('turns the error shape into an ApiError with field details', async () => {
    mockApi({
      'POST /employees': () => ({
        status: 422,
        body: { error: { code: 'invalid', message: 'Some fields are not valid.', details: { fields: { email: 'bad email' } } } },
      }),
    })
    const error = await api('/employees', { method: 'POST', body: {} }).then(failIfResolved, (e: ApiError) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(422)
    expect(error.fields).toEqual({ email: 'bad email' })
  })

  it('sends JSON with the Idempotency-Key header', async () => {
    const fetchMock = mockApi({ 'POST /employees/1/salaries': () => ({ status: 201, body: { ok: true } }) })
    await api('/employees/1/salaries', { method: 'POST', body: { amount: '100.00' }, idempotencyKey: 'key-1' })
    const [, init] = fetchMock.mock.calls[0]
    expect((init!.headers as Record<string, string>)['Idempotency-Key']).toBe('key-1')
    expect(init!.body).toBe('{"amount":"100.00"}')
  })

  it('returns undefined for 204', async () => {
    mockApi({ 'DELETE /employees/1/photo': () => ({ status: 204 }) })
    await expect(api('/employees/1/photo', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it('reports a network failure in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await api('/meta').then(failIfResolved, (e: ApiError) => e)
    expect(error.code).toBe('network')
    expect(errorMessage(error)).toMatch(/Can't reach the server/)
  })
})

describe('errorMessage', () => {
  it('uses retry_after for rate limits', () => {
    expect(errorMessage(new ApiError(429, 'rate_limited', 'x', { retry_after: 20 }))).toBe(
      "You're going a bit fast. Try again in 20 seconds.",
    )
  })

  it('passes through the server message, with a fallback for unknown errors', () => {
    expect(errorMessage(new ApiError(409, 'version_conflict', 'Changed by someone else.'))).toBe('Changed by someone else.')
    expect(errorMessage(new Error('boom'))).toBe('Something went wrong. Try again.')
  })
})

describe('toQuery', () => {
  it('repeats array keys and drops empty values', () => {
    expect(toQuery({ country: ['IN', 'US'], q: '', page: 2, outliers_only: false, x: undefined })).toBe(
      '?country=IN&country=US&page=2',
    )
    expect(toQuery({})).toBe('')
  })
})
