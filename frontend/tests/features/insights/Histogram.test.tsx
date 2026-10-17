import { render, screen } from '@testing-library/react'
import { cloneElement, type ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

import Histogram, { BinTooltip } from '@/features/insights/Histogram'

// jsdom has no layout, so the responsive wrapper measures 0×0 and draws nothing; give it a size.
vi.mock('recharts', async (original) => ({
  ...(await original<typeof import('recharts')>()),
  ResponsiveContainer: ({ children }: { children: ReactElement<{ width: number; height: number }> }) =>
    cloneElement(children, { width: 400, height: 200 }),
}))

const bins = (...counts: number[]) => counts.map((count, i) => ({ start: String(i * 500000), end: String((i + 1) * 500000), count }))

function bars(container: HTMLElement) {
  return [...container.querySelectorAll('.recharts-bar-rectangle path')].map((bar) => bar.getAttribute('fill'))
}

describe('Histogram', () => {
  it('describes the range and marks the bracket holding the median', () => {
    const { container } = render(<Histogram data={{ currency: 'INR', bins: bins(3, 9, 2) }} />)
    expect(screen.getByRole('img')).toHaveAccessibleName('14 salaries from ₹0 to ₹15,00,000')
    expect(bars(container)).toEqual(['var(--color-band)', 'var(--color-primary)', 'var(--color-band)'])
  })

  it('marks the first bracket when it holds exactly half', () => {
    const { container } = render(<Histogram data={{ currency: 'USD', bins: bins(5, 0, 5) }} />)
    expect(bars(container)[0]).toBe('var(--color-primary)')
  })

  it('labels the axis in short money', () => {
    const { container } = render(<Histogram data={{ currency: 'USD', bins: bins(1, 1) }} />)
    const ticks = [...container.querySelectorAll('.recharts-xAxis-tick-labels text')].map((t) => t.textContent)
    expect(ticks).toContain('$500K')
  })

  it('says so when there are no salaries', () => {
    render(<Histogram data={{ currency: 'USD', bins: bins(0, 0) }} />)
    expect(screen.getByText('No salaries to show.')).toBeInTheDocument()
  })
})

describe('BinTooltip', () => {
  const bin = { start: '1000000', end: '1500000', count: 1234 }

  it('shows the hovered bracket and how many people are in it', () => {
    render(<BinTooltip currency="INR" active payload={[{ payload: bin }]} />)
    expect(screen.getByText('₹10,00,000 to ₹15,00,000: 1,234 people')).toBeInTheDocument()
  })

  it('shows nothing when not hovering or with no bin', () => {
    const { container, rerender } = render(<BinTooltip currency="INR" active={false} payload={[{ payload: bin }]} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<BinTooltip currency="INR" active payload={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
