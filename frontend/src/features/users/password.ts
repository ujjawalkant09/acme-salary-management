/** The same rule as the API: 8 to 200 characters. */
export function passwordError(password: string): string | undefined {
  if (password.length < 8) return 'Use at least 8 characters.'
  if (password.length > 200) return 'Use at most 200 characters.'
}
