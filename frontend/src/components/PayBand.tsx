// The one signature element (05-UI §2): a range line (lowest to highest), a shaded bar for
// the middle half, a blue tick for the median and, for one person, a dot.

export interface BandStats {
  min: string
  p25: string
  median: string
  p75: string
  max: string
}

interface PayBandProps {
  stats: BandStats
  /** The person's own salary, drawn as a dot. */
  value?: string
  /** Paid outside the usual range: the dot is amber. */
  outlier?: boolean
  width?: number
  /** Fixed scale so several bands in one table line up. Defaults to the band's own range. */
  scale?: { lo: number; hi: number }
  label: string
}

const PAD = 6

export function PayBand({ stats, value, outlier = false, width = 220, scale, label }: PayBandProps) {
  // Positions only: converting to numbers here is for drawing, not for storing money.
  const min = Number(stats.min)
  const max = Number(stats.max)
  const own = value === undefined ? undefined : Number(value)
  const lo = scale?.lo ?? Math.min(min, own ?? min)
  const hi = scale?.hi ?? Math.max(max, own ?? max)
  const span = hi - lo || 1
  const x = (v: number) => PAD + ((Math.min(Math.max(v, lo), hi) - lo) / span) * (width - 2 * PAD)

  const p25 = x(Number(stats.p25))
  const p75 = x(Number(stats.p75))
  return (
    <svg
      viewBox={`0 0 ${width} 22`}
      // Sized in rem (not px) so the band grows with the rest of the UI.
      style={{ width: `${width / 16}rem` }}
      className="h-auto max-w-full"
      role="img"
      aria-label={label}
    >
      <line x1={x(min)} x2={x(max)} y1={11} y2={11} stroke="var(--color-band-line)" strokeWidth={1.2} />
      <rect x={p25} y={6} width={Math.max(2, p75 - p25)} height={10} rx={3} fill="var(--color-band)" />
      <rect x={x(Number(stats.median)) - 1} y={4} width={2} height={14} rx={1} fill="var(--color-primary)" />
      {own !== undefined && (
        <circle
          data-testid="payband-dot"
          cx={x(own)}
          cy={11}
          r={5.5}
          fill="#fff"
          stroke={outlier ? 'var(--color-amber)' : 'var(--color-foreground)'}
          strokeWidth={2}
        />
      )}
    </svg>
  )
}
