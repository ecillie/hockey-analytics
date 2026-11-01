import { parseLogLevel, shouldLog, type BrowserDiagnostics, type DeploymentEnvironment, type Diagnostic, type DiagnosticSink, type LogLevel } from './domain'
import { isExpectedAbort, normalizeDiagnostic } from './format'

export type LoggerOptions = Readonly<{
  level?: LogLevel
  environment?: DeploymentEnvironment
  sink?: DiagnosticSink
  clock?: () => number
  timestamp?: () => string
  maximumRecords?: number
  windowMs?: number
}>

export function createConsoleSink(): DiagnosticSink {
  const methods = { DEBUG: 'debug', INFO: 'info', WARNING: 'warn', ERROR: 'error', CRITICAL: 'error' } as const
  return Object.freeze({ write(severity: LogLevel, record: string) { console[methods[severity]](record) } })
}

export function createBrowserLogger(options: LoggerOptions = {}): BrowserDiagnostics {
  const level = parseLogLevel(options.level)
  const sink = options.sink ?? createConsoleSink()
  const clock = options.clock ?? (() => performance.now())
  const timestamp = options.timestamp ?? (() => new Date().toISOString())
  const maximum = options.maximumRecords ?? 20
  const windowMs = options.windowMs ?? 60_000
  if (!Number.isInteger(maximum) || maximum < 1 || maximum > 100 || !Number.isFinite(windowMs) || windowMs < 1 || windowMs > 3_600_000) throw new Error('Browser logging limits are invalid.')
  const budgets = new Map<LogLevel, { started: number; count: number; suppressed: boolean }>()
  const reported = new WeakSet<object>()

  function readClock(): number {
    try { const value = clock(); return Number.isFinite(value) && value >= 0 ? value : 0 } catch { return 0 }
  }

  function buildPayload(entry: Diagnostic) {
    try {
      const value = timestamp()
      if (typeof value !== 'string' || value.length !== 24 || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) throw new Error('Unavailable timestamp')
      return normalizeDiagnostic(entry, value, options.environment)
    } catch {
      return { ...normalizeDiagnostic(entry, '1970-01-01T00:00:00.000Z', options.environment), timestamp_unavailable: true }
    }
  }

  function deliver(entry: Diagnostic): boolean {
    const payload = buildPayload(entry)
    const severity = payload.severity as LogLevel
    if (!shouldLog(level, severity)) return false
    const now = readClock()
    let budget = budgets.get(severity)
    if (budget === undefined || now - budget.started >= windowMs) {
      budget = { started: now, count: 0, suppressed: false }
      budgets.set(severity, budget)
    }
    if (budget.count >= maximum) {
      if (budget.suppressed) return false
      budget.suppressed = true
      payload.event = 'logging.suppressed'
      payload.message = 'Repeated diagnostics suppressed'
    } else budget.count += 1
    let rendered: string
    let deliveredSeverity = severity
    try { rendered = JSON.stringify(payload) } catch {
      deliveredSeverity = shouldLog('ERROR', severity) ? severity : 'ERROR'
      rendered = `{"timestamp":"1970-01-01T00:00:00.000Z","timestamp_unavailable":true,"severity":"${deliveredSeverity}","event":"logging.format_failed","component":"logging","message":"Diagnostic formatting failed"}`
    }
    try { sink.write(deliveredSeverity, rendered); return true } catch { return false }
  }

  function emit(entry: Diagnostic): void {
    try { deliver(entry) } catch { return }
  }

  function report(error: unknown, entry: Diagnostic): void {
    try {
      if (isExpectedAbort(error)) return
      const object = (typeof error === 'object' && error !== null) || typeof error === 'function'
      if (object && reported.has(error)) return
      if (deliver(entry) && object) reported.add(error)
    } catch { return }
  }

  return Object.freeze({ emit, report })
}
