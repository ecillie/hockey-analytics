export const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const
export type LogLevel = typeof logLevels[number]

const priorities: Readonly<Record<LogLevel, number>> = Object.freeze({
  DEBUG: 10,
  INFO: 20,
  WARNING: 30,
  ERROR: 40,
  CRITICAL: 50,
})

export function parseLogLevel(value: string | undefined): LogLevel {
  if (value === undefined) return 'INFO'
  const normalized = value.trim().toUpperCase()
  if (logLevels.includes(normalized as LogLevel)) return normalized as LogLevel
  throw new Error('VITE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL.')
}

export function shouldLog(threshold: LogLevel, severity: LogLevel): boolean {
  return priorities[severity] >= priorities[threshold]
}

export const browserEvents = [
  'app.started', 'api.request_started', 'api.request_finished', 'api.request_failed', 'api.request_cancelled',
  'react.render_failed', 'react.uncaught_error', 'react.recovered_error', 'global.error', 'global.unhandled_rejection',
  'logging.suppressed', 'logging.format_failed', 'logging.invalid_event',
] as const
export const components = ['app', 'api', 'react', 'global', 'logging'] as const
export const failureCategories = ['network', 'http', 'decode', 'invalid_response', 'unexpected', 'render', 'unhandled', 'unknown'] as const
export const deploymentEnvironments = ['dev', 'nonprod', 'prod'] as const
export const apiRoutes = [
  '/api/health', '/api/seasons', '/api/overview', '/api/players', '/api/players/compare',
  '/api/rankings/hockey-value', '/api/search', '/api/teams',
  '/api/players/{id}', '/api/players/{id}/stats', '/api/players/{id}/seasons', '/api/players/{id}/value',
  '/api/players/{id}/value/history', '/api/players/{id}/contract', '/api/teams/{id}',
  '/api/teams/{id}/roster', '/api/teams/{id}/contracts', '/api/teams/{id}/cap', 'unknown',
] as const

export type ApiRoute = typeof apiRoutes[number]
export type DeploymentEnvironment = typeof deploymentEnvironments[number]

export function parseDeploymentEnvironment(value: string | undefined): DeploymentEnvironment | undefined {
  const normalized = value?.trim().toLowerCase()
  return deploymentEnvironments.find((environment) => environment === normalized)
}
export type Diagnostic = Readonly<{
  event: typeof browserEvents[number]
  severity: LogLevel
  component: typeof components[number]
  category?: typeof failureCategories[number]
  route?: ApiRoute
  requestId?: string
  status?: number
  durationMs?: number
}>

export interface BrowserDiagnostics {
  emit(entry: Diagnostic): void
  report(error: unknown, entry: Diagnostic): void
}

export interface DiagnosticSink {
  write(severity: LogLevel, record: string): void
}
