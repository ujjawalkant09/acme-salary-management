import { Toaster as Sonner } from 'sonner'

export function Toaster() {
  return (
    <Sonner
      position="bottom-right"
      toastOptions={{
        style: {
          background: 'var(--color-foreground)',
          color: '#fff',
          border: 0,
          fontFamily: 'var(--font-sans)',
          fontWeight: 500,
        },
      }}
    />
  )
}
