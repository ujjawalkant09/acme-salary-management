import { describe, expect, it } from 'vitest'

import { fileSize, formatDate, money, plural, signedPct, usd } from '@/lib/format'

describe('money', () => {
  it("uses each country's own number format", () => {
    expect(money('1840000.00', 'INR')).toBe('₹18,40,000')
    expect(money('202500.00', 'BRL')).toBe('R$ 202.500')
    expect(money('64500.00', 'USD')).toBe('$64,500')
  })

  it('formats decimal strings without turning them into floats', () => {
    // 2^53 + 1 cannot be represented as a float; as a string it stays exact.
    expect(money('9007199254740993', 'USD')).toBe('$9,007,199,254,740,993')
  })

  it('rounds to whole units for display and supports compact', () => {
    expect(usd('1234.56')).toBe('$1,235')
    expect(usd('1250000000', true)).toBe('$1.3B')
  })
})

describe('other formatting', () => {
  it('formats dates in UTC so a date never shifts by a day', () => {
    expect(formatDate('2026-04-01')).toBe('1 Apr 2026')
  })

  it('signs percentages with a real minus sign', () => {
    expect(signedPct('8.24')).toBe('+8.2%')
    expect(signedPct('-3')).toBe('−3.0%')
    expect(signedPct('0')).toBe('0.0%')
  })

  it('pluralises and sizes files', () => {
    expect(plural(1, 'person', 'people')).toBe('1 person')
    expect(plural(1200, 'person', 'people')).toBe('1,200 people')
    expect(fileSize(200)).toBe('1 KB')
    expect(fileSize(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
