import { useRef, useState, type FormEvent } from 'react'

import { Logo } from '@/components/Logo'
import { Spinner } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError, errorMessage } from '@/lib/api'
import { useLogin } from '@/lib/auth'

// The two demo logins created by the seed script. Passwords are shared with reviewers
// separately and are never in the code.
const DEMO_ACCOUNTS = [
  { email: 'priya.sharma@acme.example', title: 'HR Admin', text: 'Priya Sharma: can view and change everything' },
  { email: 'arjun.mehta@acme.example', title: 'HR Viewer', text: 'Arjun Mehta: can view everything, change nothing' },
]

export default function LoginPage() {
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const passwordRef = useRef<HTMLInputElement>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    login.mutate({ email: email.trim(), password })
  }

  const error =
    login.error instanceof ApiError && login.error.status === 401
      ? 'That email and password don\'t match. Check them and try again.'
      : login.error && errorMessage(login.error)

  return (
    <div className="grid min-h-full place-items-center bg-side p-6">
      <form
        onSubmit={submit}
        className="w-[23.75rem] max-w-full rounded-xl border border-border bg-background p-8"
        noValidate
      >
        <div className="pb-6">
          <Logo />
        </div>
        <h1 className="text-[1.375rem] font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 mb-2 text-muted">Salary management for the HR team.</p>

        <div className="mt-4 flex flex-col gap-1.5">
          <Label htmlFor="email">Work email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="mt-4 flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            ref={passwordRef}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p className="mt-3 text-sm text-error" role="alert">
            {error}
          </p>
        )}
        <Button
          type="submit"
          className="mt-5 w-full"
          disabled={login.isPending || !email.trim() || !password}
        >
          {login.isPending && <Spinner />}
          Sign in
        </Button>

        <p className="mt-4 rounded-md bg-subtle px-3 py-2.5 text-sm text-muted">
          This is a demo. Pick a demo account to fill in its email, then enter the password you were given.
        </p>
        <div className="mt-5 grid gap-2">
          {DEMO_ACCOUNTS.map((account) => (
            <button
              key={account.email}
              type="button"
              onClick={() => {
                setEmail(account.email)
                passwordRef.current?.focus()
              }}
              className="flex cursor-pointer flex-col items-start gap-0.5 rounded-md border border-border px-3.5 py-3 text-left hover:border-primary hover:bg-primary-soft"
            >
              <b className="font-semibold">{account.title}</b>
              <span className="text-sm text-muted">{account.text}</span>
            </button>
          ))}
        </div>
      </form>
    </div>
  )
}
