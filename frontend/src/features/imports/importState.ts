import { count } from '@/lib/format'
import type { ImportJob, ImportStatus } from '@/lib/types'
import { MAX_FILE_BYTES } from '@/lib/upload'

const OPEN: ImportStatus[] = ['queued', 'validating', 'validated', 'commit_queued', 'committing']
const WORKING: ImportStatus[] = ['queued', 'validating', 'commit_queued', 'committing']

/** Still open: waiting for the worker or for the person to review it. */
export function isOpen(status: ImportStatus): boolean {
  return OPEN.includes(status)
}

/** The worker is busy with it, so the page polls. */
export function isWorking(status: ImportStatus): boolean {
  return WORKING.includes(status)
}

/** Which step of Upload → Check → Review → Apply → Done a job is on (1-based). */
export function stepOf(status: ImportStatus | undefined): number {
  switch (status) {
    case 'queued':
    case 'validating':
      return 2
    case 'validated':
      return 3
    case 'commit_queued':
    case 'committing':
      return 4
    case 'completed':
      return 5
    default:
      return 1
  }
}

export function importFileError(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!name.endsWith('.xlsx') && !name.endsWith('.csv')) return 'Choose an Excel (.xlsx) or CSV file.'
  if (file.size > MAX_FILE_BYTES) return 'This file is larger than 10 MB. Split it into smaller files.'
  if (file.size === 0) return 'This file is empty.'
  return null
}

export function resultText(job: ImportJob): string {
  switch (job.status) {
    case 'completed':
      return `${count(job.updated_count)} updated, ${count(job.created_count)} added`
    case 'failed':
      return job.error_message ?? 'Failed'
    case 'cancelled':
      return 'Cancelled, nothing changed'
    case 'validated':
      return 'Waiting for review'
    default:
      return 'In progress'
  }
}
