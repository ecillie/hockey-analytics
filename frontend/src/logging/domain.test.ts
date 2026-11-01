import { describe, expect, it } from 'vitest'
import { logLevels, parseLogLevel, shouldLog } from './domain'

describe('browser diagnostic thresholds', () => {
  it('defaults to INFO without depending on environment or API mode', () => {
    expect(logLevels).toEqual(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    expect(parseLogLevel(undefined)).toBe('INFO')
  })

  it.each(logLevels)('normalizes %s case and whitespace', (level) => {
    expect(parseLogLevel(` ${level.toLowerCase()} `)).toBe(level)
  })

  it.each(['', '   ', 'warn', 'trace', 'password_secret\nvalue'])('rejects invalid settings without echoing the input (%j)', (value) => {
    expect(() => parseLogLevel(value)).toThrow('VITE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL.')
    expect(() => parseLogLevel(value)).not.toThrow('password_secret')
  })

  it.each(logLevels)('filters all severities at %s', (threshold) => {
    expect(logLevels.filter((severity) => shouldLog(threshold, severity)))
      .toEqual(logLevels.slice(logLevels.indexOf(threshold)))
  })
})
