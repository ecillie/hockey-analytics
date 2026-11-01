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
