// Thin fetch wrapper for /api/v1. Every error becomes an ApiError with the backend's
// {"error": {"code", "message", "details"}} shape.

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  /** Per-field messages from a 422 response. */
  get fields(): Record<string, string> {
    return (this.details.fields as Record<string, string> | undefined) ?? {}
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  /** One key per user action, reused on retries, so the server applies it only once. */
  idempotencyKey?: string
  signal?: AbortSignal
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, idempotencyKey, signal } = options
  const headers: Record<string, string> = { Accept: 'application/json' }
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey

  let response: Response
  try {
    response = await fetch(API_BASE + path, {
      method,
      headers,
      body: payload,
      signal,
      credentials: 'same-origin',
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network', "Can't reach the server. Check your connection and try again.")
  }

  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const err = data?.error
    throw new ApiError(
      response.status,
      err?.code ?? 'error',
      err?.message ?? 'Something went wrong. Try again.',
      err?.details ?? {},
    )
  }
  return data as T
}

/** Builds a query string; arrays become repeated keys, empty values are left out. */
export function toQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    const values = Array.isArray(value) ? value : [value]
    for (const v of values) {
      if (v === undefined || v === null || v === '' || v === false) continue
      search.append(key, String(v))
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

/** The message to show a person for any error thrown by `api`. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) {
      const seconds = Number(error.details.retry_after) || 20
      return `You're going a bit fast. Try again in ${seconds} seconds.`
    }
    return error.message
  }
  return 'Something went wrong. Try again.'
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}
