import { expect, it } from 'vitest'

import { passwordError } from '@/features/users/password'

it('accepts 8 to 200 characters, the same as the API', () => {
  expect(passwordError('1234567')).toBe('Use at least 8 characters.')
  expect(passwordError('12345678')).toBeUndefined()
  expect(passwordError('x'.repeat(200))).toBeUndefined()
  expect(passwordError('x'.repeat(201))).toBe('Use at most 200 characters.')
})
