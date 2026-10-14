import { Progress as ProgressPrimitive } from 'radix-ui'

export function Progress({ value, label }: { value: number; label: string }) {
  return (
    <ProgressPrimitive.Root
      value={value}
      aria-label={label}
      className="my-4 h-1.5 overflow-hidden rounded-full border border-border bg-subtle"
    >
      <ProgressPrimitive.Indicator
        className="h-full bg-primary transition-[width] duration-200"
        style={{ width: `${value}%` }}
      />
    </ProgressPrimitive.Root>
  )
}
