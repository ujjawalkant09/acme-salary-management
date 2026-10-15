import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { count, money } from '@/lib/format'
import type { Distribution } from '@/lib/types'

export default function Histogram({ data }: { data: Distribution }) {
  const total = data.bins.reduce((sum, b) => sum + b.count, 0)
  if (total === 0) return <p className="text-muted">No salaries to show.</p>

  const medianIndex = medianBin(data.bins.map((b) => b.count), total)
  const rows = data.bins.map((b) => ({ ...b, mid: Number(b.start) }))

  return (
    <div className="h-[13.75rem]" role="img" aria-label={`${count(total)} salaries from ${money(data.bins[0].start, data.currency)} to ${money(data.bins[data.bins.length - 1].end, data.currency)}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={3}>
          <XAxis
            dataKey="mid"
            tickFormatter={(v: number) => money(v, data.currency, true)}
            tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--color-border)' }}
            minTickGap={24}
          />
          <YAxis allowDecimals={false} width={36} tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} />
          <Tooltip cursor={{ fill: 'var(--color-subtle)' }} content={<BinTooltip currency={data.currency} />} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {rows.map((row, i) => (
              <Cell key={row.start} fill={i === medianIndex ? 'var(--color-primary)' : 'var(--color-band)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

type Bin = Distribution['bins'][number]

/** Recharts fills in `active` and `payload` (the hovered bin) when it shows the tooltip. */
export function BinTooltip({ currency, active, payload }: { currency: string; active?: boolean; payload?: readonly { payload?: Bin }[] }) {
  const bin = active ? payload?.[0]?.payload : undefined
  if (!bin) return null
  return (
    <div className="rounded-md border border-border bg-background px-2.5 py-1.5 text-sm shadow-sm">
      {money(bin.start, currency)} to {money(bin.end, currency)}: {count(bin.count)} people
    </div>
  )
}

/** The bracket holding the median, drawn in the primary colour like the pay band's median tick.
 *  Needs `total > 0`, so the running count always reaches half of it. */
function medianBin(counts: number[], total: number): number {
  let running = 0
  return counts.findIndex((n) => (running += n) >= total / 2)
}
