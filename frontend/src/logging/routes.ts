import { apiRoutes, type ApiRoute } from './domain'

export function diagnosticRoute(path: string): ApiRoute {
  const pathname = path.split(/[?#]/, 1)[0]
  if (apiRoutes.includes(pathname as ApiRoute) && !pathname.includes('{')) return pathname as ApiRoute
  const template = pathname.replace(/^(\/api\/(?:players|teams))\/\d+(?=\/|$)/, '$1/{id}')
  return apiRoutes.includes(template as ApiRoute) ? template as ApiRoute : 'unknown'
}
