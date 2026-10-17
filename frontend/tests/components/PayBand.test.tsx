import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PayBand } from '@/components/PayBand'

const stats = { min: '100', p25: '200', median: '300', p75: '400', max: '500' }

describe('PayBand', () => {
  it('draws the range, the middle half and the median, labelled for screen readers', () => {
    const { container } = render(<PayBand stats={stats} width={212} label="Pay range" />)
    expect(screen.getByRole('img', { name: 'Pay range' })).toBeInTheDocument()
    const [line] = container.querySelectorAll('line')
    const [band, median] = container.querySelectorAll('rect')
    // 6px padding, 200px of drawing width for 100..500.
    expect(line.getAttribute('x1')).toBe('6')
    expect(line.getAttribute('x2')).toBe('206')
    expect(band.getAttribute('x')).toBe('56')
    expect(band.getAttribute('width')).toBe('100')
    expect(median.getAttribute('x')).toBe('105')
    expect(screen.queryByTestId('payband-dot')).toBeNull()
  })

  it('marks the person, in amber when their pay is unusual', () => {
    const { rerender } = render(<PayBand stats={stats} value="300" label="x" />)
    expect(screen.getByTestId('payband-dot').getAttribute('stroke')).toBe('var(--color-foreground)')
    rerender(<PayBand stats={stats} value="900" outlier label="x" />)
    expect(screen.getByTestId('payband-dot').getAttribute('stroke')).toBe('var(--color-amber)')
  })

  it('stretches to include a person outside the range, and clamps to a fixed scale', () => {
    const { rerender } = render(<PayBand stats={stats} value="900" width={212} label="x" />)
    expect(screen.getByTestId('payband-dot').getAttribute('cx')).toBe('206')
    rerender(<PayBand stats={stats} value="900" width={212} scale={{ lo: 0, hi: 600 }} label="x" />)
    expect(screen.getByTestId('payband-dot').getAttribute('cx')).toBe('206')
  })

  it('does not break when every salary is the same', () => {
    const flat = { min: '5', p25: '5', median: '5', p75: '5', max: '5' }
    const { container } = render(<PayBand stats={flat} label="x" />)
    expect(container.querySelector('rect')?.getAttribute('width')).toBe('2')
  })
})
