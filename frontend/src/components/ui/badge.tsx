import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center whitespace-nowrap rounded-full border px-2 py-px text-xs font-medium',
  {
    variants: {
      variant: {
        default: 'border-border text-muted',
        blue: 'border-transparent bg-primary-soft text-primary',
        warn: 'border-transparent bg-amber-soft text-amber',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export function Badge({
  className,
  variant,
  ...props
}: ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
