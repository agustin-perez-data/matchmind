// Sign-in for the club area, from Azure Static Web Apps' built-in providers (GitHub and Microsoft, no app
// registration). The demo never calls any of this: only /club and /signin do.
export type Provider = 'github' | 'aad'
export type Me = { name: string; provider: string }

export const PROVIDERS: { id: Provider; label: string }[] = [
  { id: 'github', label: 'Sign in with GitHub' },
  { id: 'aad', label: 'Sign in with Microsoft' },
]

export const LOGOUT_URL = '/.auth/logout?post_logout_redirect_uri=/'

export function loginUrl(provider: Provider, next = '/club'): string {
  return `/.auth/login/${provider}?post_login_redirect_uri=${encodeURIComponent(next)}`
}

/** The /.auth/me payload as a person: null when anonymous or when there is no /.auth (local dev). */
export function parseMe(payload: unknown): Me | null {
  const p = (payload as { clientPrincipal?: { userDetails?: string; identityProvider?: string } | null } | null)?.clientPrincipal
  if (!p || !p.userDetails) return null
  return { name: p.userDetails, provider: p.identityProvider ?? 'unknown' }
}

export async function getMe(): Promise<Me | null> {
  try {
    const r = await fetch('/.auth/me')
    if (!r.ok) return null
    return parseMe(await r.json())
  } catch {
    return null
  }
}
