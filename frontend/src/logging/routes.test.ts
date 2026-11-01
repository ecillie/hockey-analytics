import { describe, expect, it } from 'vitest'
import { apiRoutes } from './domain'
import { diagnosticRoute } from './routes'

describe('safe diagnostic routes', () => {
  it.each(apiRoutes.filter((route) => route !== 'unknown'))('classifies %s without query values', (route) => {
    expect(diagnosticRoute(`${route.replace('{id}', '123')}?secret=private#fragment`)).toBe(route)
  })

  it.each(['/api/players/private', '/api/unknown?secret=private', 'https://private.example/api/players', '/api/players/{id}/unknown'])('redacts unknown paths: %s', (path) => {
    expect(diagnosticRoute(path)).toBe('unknown')
  })
})
