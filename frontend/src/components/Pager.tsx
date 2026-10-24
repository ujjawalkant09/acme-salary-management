import { Button } from '@/components/ui/button'
import { count } from '@/lib/format'
import type { Page } from '@/lib/types'

/** "21–40 of 312" with Previous / Next buttons for any paged API response. */
export function Pager({ data, onPage }: { data: Page<unknown>; onPage: (page: number) => void }) {
  const first = (data.page - 1) * data.page_size + 1
  const last = Math.min(data.page * data.page_size, data.total)
  return (
    <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2">
      <span className="text-sm text-muted">
        {count(first)}–{count(last)} of {count(data.total)}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>
          Previous
        </Button>
        <span className="px-1.5 text-sm text-muted">
          Page {count(data.page)} of {count(Math.max(1, data.pages))}
        </span>
        <Button variant="outline" size="sm" disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}
