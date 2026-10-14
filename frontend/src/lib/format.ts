// Display formatting. Amounts arrive as decimal strings and are passed to Intl as strings,
// so no money value is ever turned into a float.

const LOCALE_BY_CURRENCY: Record<string, string> = {
  INR: 'en-IN',
  USD: 'en-US',
  CAD: 'en-CA',
  SGD: 'en-SG',
  BRL: 'pt-BR',
  AUD: 'en-AU',
}

const formatters = new Map<string, Intl.NumberFormat>()

function formatter(currency: string, compact: boolean): Intl.NumberFormat {
  const key = `${currency}:${compact}`
  let nf = formatters.get(key)
  if (!nf) {
    nf = new Intl.NumberFormat(LOCALE_BY_CURRENCY[currency] ?? 'en-US', {
      style: 'currency',
      currency,
      maximumFractionDigits: compact ? 1 : 0,
      notation: compact ? 'compact' : 'standard',
    })
    formatters.set(key, nf)
  }
  return nf
}

/** "₹18,40,000", "R$ 202.500", "$64,500"; `compact` gives "$1.2B". */
export function money(amount: string | number, currency: string, compact = false): string {
  return formatter(currency, compact).format(amount as Intl.StringNumericLiteral)
}

export function usd(amount: string | number, compact = false): string {
  return money(amount, 'USD', compact)
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})

/** "14 Oct 2026" from "2026-10-14" or a full ISO timestamp. */
export function formatDate(iso: string): string {
  const date = iso.length === 10 ? new Date(`${iso}T00:00:00Z`) : new Date(iso)
  return dateFormat.format(date)
}

/** "+8.2%" / "−3.0%" from a percentage string like "8.24". */
export function signedPct(pct: string | number, digits = 1): string {
  const n = Number(pct)
  const sign = n > 0 ? '+' : n < 0 ? '−' : ''
  return `${sign}${Math.abs(n).toFixed(digits)}%`
}

export function count(n: number): string {
  return n.toLocaleString('en-US')
}

export function plural(n: number, one: string, many: string): string {
  return `${count(n)} ${n === 1 ? one : many}`
}

export function initials(first: string, last: string): string {
  return `${first[0] ?? ''}${last[0] ?? ''}`.toUpperCase()
}

export function fileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const LABELS: Record<string, string> = {
  full_time: 'Full-time',
  part_time: 'Part-time',
  contractor: 'Contractor',
  hire: 'Hire',
  promotion: 'Promotion',
  merit: 'Merit',
  market_adjustment: 'Market adjustment',
  correction: 'Correction',
  other: 'Other',
  female: 'Female',
  male: 'Male',
  non_binary: 'Non-binary',
  undisclosed: 'Prefer not to say',
  active: 'Current employee',
  left: 'Left the company',
}

/** Human label for an enum value from the API. */
export function label(value: string): string {
  return LABELS[value] ?? value
}

/** Today's date as YYYY-MM-DD in the person's time zone. */
export function todayIso(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
