import { describe, expect, it } from 'vitest'
import { loginUrl, parseMe } from './auth'

describe('club sign-in helpers', () => {
  it('reads the signed-in person from /.auth/me and nothing else', () => {
    expect(parseMe({ clientPrincipal: { userDetails: 'agustin', identityProvider: 'github' } })).toEqual({ name: 'agustin', provider: 'github' })
    expect(parseMe({ clientPrincipal: null })).toBeNull()
    expect(parseMe(null)).toBeNull()
    expect(parseMe({})).toBeNull()
  })

  it('sends the person back to the club area after signing in', () => {
    expect(loginUrl('github')).toBe('/.auth/login/github?post_login_redirect_uri=%2Fclub')
    expect(loginUrl('aad', '/club?x=1')).toBe('/.auth/login/aad?post_login_redirect_uri=%2Fclub%3Fx%3D1')
  })
})
