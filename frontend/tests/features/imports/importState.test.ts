import { describe, expect, it } from 'vitest'

import type { ImportJob } from '@/lib/types'

import { importFileError, isOpen, isWorking, resultText, stepOf } from '@/features/imports/importState'

const file = (name: string, size: number) => new File([new Uint8Array(size)], name)

describe('import state', () => {
  it('maps each status to its step', () => {
    expect(stepOf(undefined)).toBe(1)
    expect(stepOf('queued')).toBe(2)
    expect(stepOf('validating')).toBe(2)
    expect(stepOf('validated')).toBe(3)
    expect(stepOf('committing')).toBe(4)
    expect(stepOf('completed')).toBe(5)
    expect(stepOf('cancelled')).toBe(1)
  })

  it('knows which statuses are open and which need polling', () => {
    expect(isOpen('validated')).toBe(true)
    expect(isWorking('validated')).toBe(false)
    expect(isWorking('commit_queued')).toBe(true)
    expect(isOpen('completed')).toBe(false)
  })

  it('checks files before upload', () => {
    expect(importFileError(file('people.xlsx', 10))).toBeNull()
    expect(importFileError(file('people.CSV', 10))).toBeNull()
    expect(importFileError(file('macros.xlsm', 10))).toMatch(/Excel \(.xlsx\) or CSV/)
    expect(importFileError(file('people.csv', 0))).toBe('This file is empty.')
    expect(importFileError(file('big.csv', 10 * 1024 * 1024 + 1))).toMatch(/larger than 10 MB/)
  })

  it('summarises past imports', () => {
    const job = { status: 'completed', updated_count: 1204, created_count: 42 } as ImportJob
    expect(resultText(job)).toBe('1,204 updated, 42 added')
    expect(resultText({ ...job, status: 'cancelled' })).toBe('Cancelled, nothing changed')
    expect(resultText({ ...job, status: 'failed', error_message: 'Bad file' })).toBe('Bad file')
  })
})
