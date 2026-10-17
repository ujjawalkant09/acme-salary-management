import { describe, expect, it } from 'vitest'

import { META } from '@tests/support/utils'

import { countryName, currencyOf } from '@/lib/meta'

describe('reference data lookups', () => {
  it('finds a country name and currency', () => {
    expect(countryName(META, 'IN')).toBe('India')
    expect(currencyOf(META, 'IN')).toBe('INR')
  })

  it('falls back when the country or the data is missing', () => {
    expect(countryName(META, 'FR')).toBe('FR')
    expect(countryName(undefined, 'IN')).toBe('IN')
    expect(currencyOf(META, 'FR')).toBe('USD')
    expect(currencyOf(undefined, 'IN')).toBe('USD')
  })
})
