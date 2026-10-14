import { ToggleGroup as ToggleGroupPrimitive } from 'radix-ui'
import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

/** A segmented control ("Country | Department"). */
export function ToggleGroup({
  className,
  ...props
}: ComponentProps<typeof ToggleGroupPrimitive.Root>) {
  return (
    <ToggleGroupPrimitive.Root
      className={cn('inline-flex rounded-md border border-border bg-subtle p-0.5', className)}
      {...props}
    />
  )
}

export function ToggleGroupItem({
  className,
  ...props
}: ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  return (
    <ToggleGroupPrimitive.Item
      className={cn(
        'cursor-pointer rounded-[0.375rem] px-3 py-1 text-sm font-medium text-muted data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-[0_1px_2px_rgba(20,22,30,.08)]',
        className,
      )}
      {...props}
    />
  )
}
