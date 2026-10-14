// Pure salary helpers (form checks, hints, peer wording), kept apart so they're easy to test.
import type { PeerStats } from '@/lib/types'

const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/

/** An error message for a typed yearly salary, or null when it's valid. */
export function amountError(value: string): string | null {
  const text = value.trim()
  if (!text) return 'Enter the yearly salary.'
  if (!AMOUNT.test(text)) return 'Use numbers only, with up to 2 decimals (for example 84000 or 84000.50).'
  if (Number(text) <= 0) return 'The salary must be more than 0.'
  return null
}

export interface ChangeHint {
  pct: number
  difference: number
  /** More than 30% up or down: worth a second look. */
  big: boolean
}

/** How a new amount compares with the current one, for the live hint. Display only. */
export function changeHint(current: string, next: string): ChangeHint | null {
  if (amountError(next)) return null
  const from = Number(current)
  const to = Number(next.trim())
  if (!from || to === from) return null
  const pct = ((to - from) / from) * 100
  return { pct, difference: to - from, big: Math.abs(pct) > 30 }
}

/** Days from `fromIso` to `toIso` (both YYYY-MM-DD); negative when `toIso` is earlier. */
export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((Date.parse(`${toIso}T00:00:00Z`) - Date.parse(`${fromIso}T00:00:00Z`)) / 86_400_000)
}

export function dateHint(effectiveDate: string, today: string): { text: string; warn: boolean } | null {
  if (!effectiveDate) return null
  const days = daysBetween(today, effectiveDate)
  if (days < -90) return { text: 'This date is more than 3 months ago. It will be saved as a backdated change.', warn: true }
  if (days > 0) return { text: 'The new salary will apply from this future date.', warn: false }
  return null
}

/** The plain sentence under the pay band on the employee page. */
export function peerSentence(peers: PeerStats): string {
  const diff = Number(peers.diff_from_median_pct)
  const text =
    Math.abs(diff) < 3
      ? 'Paid about the same as the middle of this group'
      : `Paid ${Math.round(Math.abs(diff))}% ${diff > 0 ? 'more' : 'less'} than the middle of this group`
  return peers.is_outlier ? `${text}. That's unusual for this role.` : `${text}.`
}
