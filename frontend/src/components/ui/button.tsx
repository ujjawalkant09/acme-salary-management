import { cva, type VariantProps } from 'class-variance-authority'
import { Slot } from 'radix-ui'
import type { ComponentProps } from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-45 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'border-primary bg-primary text-white hover:bg-primary-hover',
        outline: 'border-border bg-background text-foreground hover:bg-subtle',
        ghost: 'border-transparent bg-transparent text-muted hover:bg-subtle hover:text-foreground',
        danger: 'border-error bg-error text-white hover:bg-error/90',
        dangerOutline: 'border-border bg-background text-error hover:bg-subtle',
        link: 'border-transparent px-0 text-primary hover:underline',
      },
      size: {
        default: 'h-9 px-3.5',
        sm: 'h-[1.875rem] px-2.5 text-sm',
        icon: 'size-9 p-0',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export function Button({
  className,
  variant,
  size,
  asChild = false,
  type = 'button',
  ...props
}: ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : 'button'
  return (
    <Comp
      className={cn(buttonVariants({ variant, size }), className)}
      type={asChild ? undefined : type}
      {...props}
    />
  )
}
