import { describe, expect, it } from 'vitest'

import type { PeerStats } from '@/lib/types'

import { amountError, changeHint, dateHint, peerSentence } from '@/lib/salary'

describe('amountError', () => {
  it.each([
    ['', 'Enter the yearly salary.'],
    ['   ', 'Enter the yearly salary.'],
    ['12,000', expect.stringMatching(/numbers only/)],
    ['-5', expect.stringMatching(/numbers only/)],
    ['100.123', expect.stringMatching(/numbers only/)],
    ['0', 'The salary must be more than 0.'],
    ['0.00', 'The salary must be more than 0.'],
  ])('rejects %j', (value, message) => {
    expect(amountError(value)).toEqual(message)
  })

  it.each(['1', '84000', '84000.5', '84000.50', '999999999999.99'])('accepts %j', (value) => {
    expect(amountError(value)).toBeNull()
  })
})

describe('changeHint', () => {
  it('describes a raise', () => {
    expect(changeHint('100000.00', '108200')).toEqual({ pct: expect.closeTo(8.2, 5), difference: 8200, big: false })
  })

  it('flags changes over 30% in either direction', () => {
    expect(changeHint('100000.00', '140000')?.big).toBe(true)
    expect(changeHint('100000.00', '60000')?.big).toBe(true)
  })

  it('shows nothing for the same amount or an invalid one', () => {
    expect(changeHint('100000.00', '100000')).toBeNull()
    expect(changeHint('100000.00', 'abc')).toBeNull()
  })
})

describe('dateHint', () => {
  it('warns about dates more than 3 months back and explains future dates', () => {
    expect(dateHint('2026-06-01', '2026-10-14')).toEqual({ text: expect.stringMatching(/more than 3 months ago/), warn: true })
    expect(dateHint('2026-07-16', '2026-10-14')).toBeNull()
    expect(dateHint('2026-11-01', '2026-10-14')).toEqual({ text: expect.stringMatching(/future date/), warn: false })
    expect(dateHint('2026-10-14', '2026-10-14')).toBeNull()
    expect(dateHint('', '2026-10-14')).toBeNull()
  })
})

describe('peerSentence', () => {
  const peers = (diff: string, outlier = false): PeerStats => ({
    count: 12,
    currency: 'INR',
    min: '1',
    p25: '2',
    median: '3',
    p75: '4',
    max: '5',
    employee_value: '3',
    diff_from_median_pct: diff,
    is_outlier: outlier,
  })

  it('says how far from the middle of the group someone is', () => {
    expect(peerSentence(peers('12.4'))).toBe('Paid 12% more than the middle of this group.')
    expect(peerSentence(peers('-8'))).toBe('Paid 8% less than the middle of this group.')
    expect(peerSentence(peers('2.9'))).toBe('Paid about the same as the middle of this group.')
    expect(peerSentence(peers('41', true))).toBe("Paid 41% more than the middle of this group. That's unusual for this role.")
  })
})
