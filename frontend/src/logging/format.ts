import { apiRoutes, browserEvents, components, deploymentEnvironments, failureCategories, logLevels, type Diagnostic } from './domain'

function selectValue<T extends string>(value: unknown, choices: readonly T[], fallback: T): T {
  return typeof value === 'string' && choices.includes(value as T) ? value as T : fallback
}

export function readRequestId(value: unknown): string | undefined {
  return typeof value === 'string' && value.length === 32 && /^[0-9a-f]{32}$/.test(value) ? value : undefined
}

export function isExpectedAbort(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError' || error instanceof DOMException && error.name === 'AbortError'
}

export function normalizeDiagnostic(entry: Diagnostic, timestamp: string, environment: unknown): Record<string, string | number | boolean> {
  const severity = selectValue(entry.severity, logLevels, 'ERROR')
  const event = selectValue(entry.event, browserEvents, 'logging.invalid_event')
  const payload: Record<string, string | number | boolean> = {
    timestamp, severity, event, component: selectValue(entry.component, components, 'logging'),
    message: event.replaceAll(/[._]/g, ' '),
  }
  if (typeof environment === 'string' && deploymentEnvironments.includes(environment as typeof deploymentEnvironments[number])) payload.environment = environment
  if (entry.category !== undefined) payload.category = selectValue(entry.category, failureCategories, 'unknown')
  if (entry.route !== undefined) payload.route = selectValue(entry.route, apiRoutes, 'unknown')
  const requestId = readRequestId(entry.requestId)
  if (requestId !== undefined) payload.request_id = requestId
  if (typeof entry.status === 'number' && Number.isInteger(entry.status) && (entry.status === 0 || entry.status >= 100 && entry.status <= 599)) payload.status = entry.status
  if (typeof entry.durationMs === 'number' && Number.isFinite(entry.durationMs) && entry.durationMs >= 0 && entry.durationMs <= 1e15) payload.duration_ms = entry.durationMs
  return payload
}
