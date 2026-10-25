import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router'

import { AddEmployeeDialog } from '@/components/AddEmployeeDialog'
import { Icon, type IconName } from '@/components/icons'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { useIsAdmin, useLogout, useUser } from '@/lib/auth'
import { initials } from '@/lib/format'
import { cn } from '@/lib/utils'

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: 'Home', icon: 'home' },
  { to: '/people', label: 'People', icon: 'users' },
  { to: '/insights', label: 'Insights', icon: 'chart' },
  { to: '/imports', label: 'Imports', icon: 'upload' },
  { to: '/changes', label: 'Salary changes', icon: 'calendar' },
]

const TITLES: Record<string, string> = {
  '/': 'Home',
  '/people': 'People',
  '/insights': 'Insights',
  '/imports': 'Imports',
  '/changes': 'Salary changes',
}

const ROLE_LABEL = { hr_admin: 'HR Admin', hr_viewer: 'HR Viewer' } as const

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const isAdmin = useIsAdmin()
  const [menuOpen, setMenuOpen] = useState(false)
  const onPeople = pathname === '/people'

  // `/` focuses search from anywhere (the People search on that page, the header search elsewhere).
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== '/' || event.metaKey || event.ctrlKey) return
      const target = event.target as HTMLElement
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable) return
      const search = document.getElementById('people-search') ?? document.getElementById('global-search')
      if (search) {
        event.preventDefault()
        search.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const title = pathname.startsWith('/people/') ? 'Employee' : (TITLES[pathname] ?? '')

  return (
    <div className="min-h-full md:grid md:grid-cols-[15rem_1fr]">
      {menuOpen && (
        <div
          className="fixed inset-0 z-40 bg-[rgba(20,22,30,.25)] md:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[16.25rem] flex-col border-r border-border bg-side px-3 py-4 transition-transform md:sticky md:top-0 md:h-screen md:w-auto md:translate-x-0',
          menuOpen ? 'translate-x-0 shadow-[16px_0_40px_rgba(20,22,30,.12)]' : '-translate-x-full',
        )}
      >
        <div className="px-2 pt-1 pb-5">
          <Logo />
        </div>
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-md px-2.5 py-2 font-medium text-muted hover:bg-subtle hover:text-foreground',
                  isActive && 'bg-background text-foreground shadow-[0_0_0_1px_var(--color-border)]',
                )
              }
            >
              <Icon name={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex-1" />
        <UserMenu />
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background px-4 md:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open menu"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" />
          </Button>
          <h1 className="text-base font-semibold">{title}</h1>
          <span className="flex-1" />
          {!onPeople && (
            <form
              role="search"
              className="relative hidden w-[13.75rem] sm:block lg:w-[18.75rem]"
              onSubmit={(e) => {
                e.preventDefault()
                const q = new FormData(e.currentTarget).get('q')?.toString().trim()
                navigate(q ? `/people?q=${encodeURIComponent(q)}` : '/people')
              }}
            >
              <Icon name="search" className="absolute top-1/2 left-2.5 size-[1.125rem] -translate-y-1/2 text-muted" />
              <Input
                id="global-search"
                name="q"
                type="search"
                placeholder="Search people"
                aria-label="Search people"
                autoComplete="off"
                className="pr-8 pl-9"
              />
              <kbd className="absolute top-1/2 right-2 -translate-y-1/2 rounded-[0.3125rem] border border-border px-1.5 text-xs text-muted">
                /
              </kbd>
            </form>
          )}
          {isAdmin && <AddEmployeeDialog />}
        </header>
        <main className="w-full px-4 pt-5 pb-10 md:px-8 md:pt-7 md:pb-14">{children}</main>
      </div>
    </div>
  )
}

function UserMenu() {
  const user = useUser()
  const logout = useLogout()
  const [first = '', last = ''] = user.name.split(' ')
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full cursor-pointer items-center gap-2.5 rounded-md border border-transparent p-2 text-left hover:border-border hover:bg-background data-[state=open]:border-border data-[state=open]:bg-background">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-white">
          {initials(first, last)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{user.name}</span>
          <span className="block text-sm text-muted">{ROLE_LABEL[user.role]}</span>
        </span>
        <Icon name="chevronsUpDown" className="size-4 text-faint" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start">
        <DropdownMenuLabel>
          <div className="font-medium">{user.name}</div>
          <div className="text-sm font-normal text-muted">{user.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => logout.mutate()}>
          <Icon name="signOut" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
