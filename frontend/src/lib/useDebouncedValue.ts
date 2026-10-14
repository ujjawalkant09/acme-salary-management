import { useEffect, useRef, useState } from 'react'

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

/**
 * A text input whose value is committed (for example to the URL) only after typing pauses.
 * If the committed value changes from outside (a "Clear all"), the input follows it.
 */
export function useDebouncedInput(
  committed: string,
  commit: (value: string) => void,
  delayMs: number,
): [string, (value: string) => void] {
  const [draft, setDraft] = useState(committed)
  const [lastCommitted, setLastCommitted] = useState(committed)
  if (committed !== lastCommitted) {
    setLastCommitted(committed)
    setDraft(committed)
  }

  // Read the latest values from refs, so only a new debounced value triggers a commit
  // (an outside change must not echo the old draft back).
  const latest = useRef({ commit, committed })
  useEffect(() => {
    latest.current = { commit, committed }
  })

  const debounced = useDebouncedValue(draft, delayMs)
  useEffect(() => {
    if (debounced !== latest.current.committed) latest.current.commit(debounced)
  }, [debounced])

  return [draft, setDraft]
}
