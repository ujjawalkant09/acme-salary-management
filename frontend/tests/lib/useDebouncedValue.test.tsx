import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDebouncedInput } from '@/lib/useDebouncedValue'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useDebouncedInput', () => {
  it('commits only after typing pauses', () => {
    const commit = vi.fn()
    const { result } = renderHook(() => useDebouncedInput('', commit, 300))
    act(() => result.current[1]('a'))
    act(() => vi.advanceTimersByTime(200))
    act(() => result.current[1]('as'))
    act(() => vi.advanceTimersByTime(299))
    expect(commit).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(commit).toHaveBeenCalledExactlyOnceWith('as')
  })

  it('follows an outside change without committing the old draft back', () => {
    const commit = vi.fn()
    const { result, rerender } = renderHook(({ value }) => useDebouncedInput(value, commit, 300), {
      initialProps: { value: 'asha' },
    })
    rerender({ value: '' })
    expect(result.current[0]).toBe('')
    act(() => vi.advanceTimersByTime(1000))
    expect(commit).not.toHaveBeenCalled()
  })
})
