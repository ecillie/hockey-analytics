import { afterEach, describe, expect, it, vi } from 'vitest'
import { logLevels, type Diagnostic, type LogLevel } from './domain'
import { createBrowserLogger, type LoggerOptions } from './logger'

const entry: Diagnostic = { event: 'api.request_failed', severity: 'ERROR', component: 'api' }
function capture(options: LoggerOptions = {}) {
  const records: Array<{ severity: LogLevel; text: string }> = []
  const logger = createBrowserLogger({ clock: () => 0, timestamp: () => '2026-11-01T00:00:00.000Z', sink: { write: (severity, text) => { records.push({ severity, text }) } }, ...options })
  return { logger, records, payloads: () => records.map(({ text }) => JSON.parse(text)) }
}

afterEach(() => vi.restoreAllMocks())

describe('safe browser diagnostics', () => {
  it.each(logLevels)('honors the %s threshold for all severities', (level) => {
    const output = capture({ level })
    logLevels.forEach((severity) => output.logger.emit({ ...entry, severity }))
    expect(output.records.map((record) => record.severity)).toEqual(logLevels.slice(logLevels.indexOf(level)))
  })

  it('selects console methods and preserves CRITICAL severity', () => {
    const methods = { debug: vi.spyOn(console, 'debug').mockImplementation(() => {}), info: vi.spyOn(console, 'info').mockImplementation(() => {}), warn: vi.spyOn(console, 'warn').mockImplementation(() => {}), error: vi.spyOn(console, 'error').mockImplementation(() => {}) }
    const logger = createBrowserLogger({ level: 'DEBUG' })
    logLevels.forEach((severity) => logger.emit({ ...entry, severity }))
    expect(methods.debug).toHaveBeenCalledOnce()
    expect(methods.info).toHaveBeenCalledOnce()
    expect(methods.warn).toHaveBeenCalledOnce()
    expect(methods.error).toHaveBeenCalledTimes(2)
    expect(JSON.parse(methods.error.mock.calls[1][0]).severity).toBe('CRITICAL')
  })

  it('omits objects, messages, stack traces and unapproved fields', () => {
    const output = capture({ environment: 'prod' })
    const secret = { toJSON: vi.fn(() => 'private_secret'), toString: vi.fn(() => { throw new Error('private_secret') }) }
    output.logger.report(secret, { ...entry, route: '/api/search', requestId: 'a'.repeat(32), category: 'http', status: 503, durationMs: 12, message: secret, headers: secret } as Diagnostic)
    expect(secret.toJSON).not.toHaveBeenCalled()
    expect(secret.toString).not.toHaveBeenCalled()
    expect(output.payloads()[0]).toMatchObject({ environment: 'prod', route: '/api/search', request_id: 'a'.repeat(32), category: 'http', status: 503, duration_ms: 12 })
    expect(output.records[0].text).not.toContain('private_secret')
    expect(output.records[0].text.length).toBeLessThan(8192)
  })

  it('uses safe markers for invalid typed fields', () => {
    const output = capture({ environment: 'private_secret' as 'prod' })
    output.logger.emit({ event: 'private_secret', severity: 'private_secret', component: 'private_secret', route: '/private_secret', category: 'private_secret', requestId: 'private_secret' } as unknown as Diagnostic)
    expect(output.payloads()[0]).toMatchObject({ event: 'logging.invalid_event', severity: 'ERROR', component: 'logging', route: 'unknown', category: 'unknown' })
    expect(output.records[0].text).not.toContain('private_secret')
    expect(output.payloads()[0]).not.toHaveProperty('environment')
  })

  it.each([null, undefined, 42, 'b'.repeat(31), 'x'.repeat(32)])('omits invalid request IDs (%j)', (requestId) => {
    const output = capture()
    output.logger.emit({ ...entry, requestId } as Diagnostic)
    expect(output.payloads()[0]).not.toHaveProperty('request_id')
  })

  it.each([0, 100, 599])('retains valid status %s', (status) => {
    const output = capture()
    output.logger.emit({ ...entry, status })
    expect(output.payloads()[0].status).toBe(status)
  })

  it.each([99, 600, 1.2, NaN, 'private_secret'])('omits invalid status (%j)', (status) => {
    const output = capture()
    output.logger.emit({ ...entry, status } as Diagnostic)
    expect(output.payloads()[0]).not.toHaveProperty('status')
  })

  it.each([-1, Infinity, 1e16, 'private_secret'])('omits invalid duration (%j)', (durationMs) => {
    const output = capture()
    output.logger.emit({ ...entry, durationMs } as Diagnostic)
    expect(output.payloads()[0]).not.toHaveProperty('duration_ms')
  })

  it.each([new Error('private_secret'), {}, () => 'private_secret'])('reports an object only once', (error) => {
    const output = capture()
    output.logger.report(error, entry)
    output.logger.report(error, entry)
    expect(output.records).toHaveLength(1)
  })

  it('does not mark errors filtered by the threshold', () => {
    const output = capture()
    const error = new Error('private_secret')
    output.logger.report(error, { ...entry, severity: 'DEBUG' })
    output.logger.report(error, entry)
    output.logger.report(null, entry)
    output.logger.report('private_secret', entry)
    expect(output.records).toHaveLength(3)
  })

  it('treats native and named aborts as expected', () => {
    const output = capture()
    const named = new Error('private_secret')
    named.name = 'AbortError'
    output.logger.report(named, entry)
    output.logger.report(new DOMException('private_secret', 'AbortError'), entry)
    output.logger.report(new DOMException('private_secret', 'DataError'), entry)
    expect(output.records).toHaveLength(1)
  })

  it('bounds loops per severity without starving ERROR behind DEBUG progress', () => {
    let now = 0
    const output = capture({ level: 'DEBUG', clock: () => now, maximumRecords: 1, windowMs: 100 })
    output.logger.emit({ ...entry, severity: 'DEBUG' })
    output.logger.emit({ ...entry, severity: 'DEBUG' })
    output.logger.emit({ ...entry, severity: 'DEBUG' })
    output.logger.emit(entry)
    expect(output.payloads().map((record) => record.event)).toEqual(['api.request_failed', 'logging.suppressed', 'api.request_failed'])
    now = 100
    output.logger.emit({ ...entry, severity: 'DEBUG' })
    expect(output.records).toHaveLength(4)
  })

  it.each([() => NaN, () => -1, () => { throw new Error('private_secret') }])('keeps delivery bounded if its monotonic clock fails', (clock) => {
    const output = capture({ clock, maximumRecords: 1 })
    output.logger.emit(entry)
    output.logger.emit(entry)
    output.logger.emit(entry)
    expect(output.records).toHaveLength(2)
  })

  it.each([() => 'private_secret', () => 'x'.repeat(24), () => 4 as unknown as string, () => { throw new Error('private_secret') }])('uses an explicit unavailable timestamp marker', (timestamp) => {
    const output = capture({ timestamp })
    output.logger.emit(entry)
    expect(output.payloads()[0]).toMatchObject({ timestamp: '1970-01-01T00:00:00.000Z', timestamp_unavailable: true })
    expect(output.records[0].text).not.toContain('private_secret')
  })

  it.each(['INFO', 'CRITICAL'] as const)('has an encoder-independent fallback at %s', (severity) => {
    const output = capture()
    vi.spyOn(JSON, 'stringify').mockImplementationOnce(() => { throw new Error('private_secret') })
    output.logger.emit({ ...entry, severity })
    expect(output.payloads()[0]).toMatchObject({ event: 'logging.format_failed', severity: severity === 'CRITICAL' ? 'CRITICAL' : 'ERROR' })
    expect(output.records[0].text).not.toContain('private_secret')
  })

  it('does not escape a broken sink or mark an undelivered exception', () => {
    const write = vi.fn().mockImplementationOnce(() => { throw new Error('private_secret') }).mockImplementationOnce(() => { throw new Error('private_secret') })
    const logger = createBrowserLogger({ sink: { write } })
    const error = new Error('private_secret')
    expect(() => logger.emit(entry)).not.toThrow()
    expect(() => logger.report(error, entry)).not.toThrow()
    logger.report(error, entry)
    expect(write).toHaveBeenCalledTimes(3)
  })

  it('does not evaluate hostile entry getters or error proxies beyond guards', () => {
    const output = capture()
    const hostile = new Proxy(entry, { get() { throw new Error('private_secret') } })
    const error = new Proxy({}, { getPrototypeOf() { throw new Error('private_secret') } })
    expect(() => output.logger.emit(hostile)).not.toThrow()
    expect(() => output.logger.report({}, hostile)).not.toThrow()
    expect(() => output.logger.report(error, entry)).not.toThrow()
    expect(output.records).toHaveLength(0)
  })

  it.each([{ maximumRecords: 0 }, { maximumRecords: 101 }, { maximumRecords: 1.5 }, { windowMs: Infinity }, { windowMs: 0 }, { windowMs: 3_600_001 }])('rejects invalid delivery limits without echoing values', (options) => {
    expect(() => createBrowserLogger(options)).toThrow('Browser logging limits are invalid.')
  })
})
