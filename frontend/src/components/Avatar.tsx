import { initials } from '@/lib/format'
import { cn } from '@/lib/utils'

export function Avatar({ first, last, className }: { first: string; last: string; className?: string }) {
  return (
    <span
      className={cn(
        'grid size-8 shrink-0 place-items-center rounded-full border border-border bg-subtle text-xs font-semibold',
        className,
      )}
    >
      {initials(first, last)}
    </span>
  )
}
