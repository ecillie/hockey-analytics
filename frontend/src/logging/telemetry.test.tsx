import { act, render } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PageViewReporter } from '../components/common/PageViewReporter'
import { createBrowserLogger } from './logger'
import {
  activatePageViews, browserPageViews, createApplicationInsightsClient, createPageViewTracker, createTelemetrySink,
  readPagePattern, removeReferrer, type TelemetryClient,
} from './telemetry'

const sdk = vi.hoisted(() => ({ config: undefined as unknown, loaded: vi.fn(), initializers: [] as unknown[] }))
vi.mock('@microsoft/applicationinsights-web', () => ({
  ApplicationInsights: class {
    constructor(options: { config: unknown }) { sdk.config = options.config }
    loadAppInsights() { sdk.loaded() }
    addTelemetryInitializer(initializer: unknown) { sdk.initializers.push(initializer) }
    trackTrace() {}
    trackException() {}
    trackPageView() {}
  },
}))

function fakeClient() {
  return { trackTrace: vi.fn(), trackException: vi.fn(), trackPageView: vi.fn() } satisfies TelemetryClient
}

afterEach(() => vi.restoreAllMocks())

describe('telemetry sink', () => {
  it('sends application records as traces with allowlisted properties', () => {
    const client = fakeClient()
    const payload = { event: 'api.request_failed', severity: 'ERROR', message: 'api request failed', route: '/api/search', status: 503 }
    createTelemetrySink(client).write('ERROR', payload)
    expect(client.trackTrace).toHaveBeenCalledExactlyOnceWith({ message: 'api request failed', severityLevel: 3 }, payload)
    expect(client.trackException).not.toHaveBeenCalled()
  })

  it.each([['react.render_failed', 'ERROR', 3], ['global.unhandled_rejection', 'CRITICAL', 4]] as const)('sends %s as an exception without a stack', (event, severity, severityLevel) => {
    const client = fakeClient()
    const payload = { event, severity, message: 'safe phrase' }
    createTelemetrySink(client).write(severity, payload)
    const [[telemetry, properties]] = client.trackException.mock.calls
    expect(telemetry.severityLevel).toBe(severityLevel)
    expect(telemetry.exception).toMatchObject({ name: event, message: 'safe phrase', stack: undefined })
    expect(properties).toBe(payload)
  })

  it('receives sanitized records from the logger in prod while console stays silent', () => {
    const client = fakeClient()
    const console = { write: vi.fn() }
    const logger = createBrowserLogger({ environment: 'prod', sink: console, telemetry: createTelemetrySink(client), clock: () => 0, timestamp: () => '2026-11-01T00:00:00.000Z' })
    logger.report(new Error('private_secret'), { event: 'api.request_failed', severity: 'ERROR', component: 'api', route: '/api/search', status: 500 })
    logger.emit({ event: 'api.request_finished', severity: 'DEBUG', component: 'api' })
    expect(console.write).not.toHaveBeenCalled()
    expect(client.trackTrace).toHaveBeenCalledOnce()
    expect(JSON.stringify(client.trackTrace.mock.calls)).not.toContain('private_secret')
    expect(client.trackTrace.mock.calls[0][1]).toMatchObject({ environment: 'prod', route: '/api/search', status: 500 })
  })

  it('rate limits telemetry like the console and contains sink failures', () => {
    const client = fakeClient()
    const logger = createBrowserLogger({ environment: 'nonprod', telemetry: createTelemetrySink(client), maximumRecords: 1, clock: () => 0 })
    const entry = { event: 'global.error', severity: 'ERROR', component: 'global' } as const
    logger.emit(entry)
    logger.emit(entry)
    logger.emit(entry)
    expect(client.trackException).toHaveBeenCalledOnce()
    expect(client.trackTrace.mock.calls[0][1]).toMatchObject({ event: 'logging.suppressed' })
    const failing = createBrowserLogger({ environment: 'prod', telemetry: { write() { throw new Error('sink') } } })
    const error = new Error('first')
    expect(() => failing.report(error, entry)).not.toThrow()
  })

  it('reports through telemetry in dev even when the console sink fails', () => {
    const client = fakeClient()
    const logger = createBrowserLogger({ environment: 'dev', sink: { write() { throw new Error('console') } }, telemetry: createTelemetrySink(client) })
    const error = new Error('once')
    logger.report(error, { event: 'global.error', severity: 'ERROR', component: 'global' })
    logger.report(error, { event: 'global.error', severity: 'ERROR', component: 'global' })
    expect(client.trackException).toHaveBeenCalledOnce()
  })
})

describe('page views', () => {
  it.each([
    ['/', '/'], ['/players', '/players'], ['/players/8478402', '/players/{id}'], ['/teams/', '/teams'],
    ['/teams/22', '/teams/{id}'], ['/compare', '/compare'], ['/about', '/about'], ['/future-plans', '/future-plans'],
    ['/players/1/extra', 'unknown'], ['/private_secret', 'unknown'],
  ])('maps %s to %s', (pathname, pattern) => {
    expect(readPagePattern(pathname)).toBe(pattern)
  })

  it('tracks route patterns instead of raw paths', () => {
    const client = fakeClient()
    const tracker = createPageViewTracker(client, 'https://app.example')
    tracker.track('/players/8478402')
    tracker.track('/private_secret')
    expect(client.trackPageView.mock.calls).toEqual([
      [{ name: '/players/{id}', uri: 'https://app.example/players/{id}' }],
      [{ name: 'unknown', uri: 'https://app.example/unknown' }],
    ])
    client.trackPageView.mockImplementation(() => { throw new Error('sink') })
    expect(() => tracker.track('/')).not.toThrow()
  })

  it('reports each router location change once activated', () => {
    const tracker = { track: vi.fn() }
    let navigate: ReturnType<typeof useNavigate> | undefined
    function Navigator() { navigate = useNavigate(); return null }
    browserPageViews.track('/ignored')
    const stop = activatePageViews(tracker)
    try {
      expect(() => activatePageViews(tracker)).toThrow('already have an owner')
      render(<MemoryRouter initialEntries={['/players?q=private_secret']}><PageViewReporter /><Navigator /></MemoryRouter>)
      act(() => navigate?.('/teams/22?q=private_secret'))
      expect(tracker.track.mock.calls).toEqual([['/players'], ['/teams/22']])
    } finally { stop() }
    stop()
    browserPageViews.track('/')
    expect(tracker.track).toHaveBeenCalledTimes(2)
    const failing = activatePageViews({ track() { throw new Error('sink') } })
    expect(() => browserPageViews.track('/')).not.toThrow()
    failing()
  })
})

describe('Application Insights client', () => {
  it('loads the SDK with cookies, storage and automatic collection off', () => {
    createApplicationInsightsClient('InstrumentationKey=test')
    expect(sdk.loaded).toHaveBeenCalledOnce()
    expect(sdk.config).toEqual({
      connectionString: 'InstrumentationKey=test',
      disableCookiesUsage: true,
      enableSessionStorageBuffer: false,
      disableAjaxTracking: true,
      disableFetchTracking: true,
      disableExceptionTracking: true,
      enableUnhandledPromiseRejectionTracking: false,
      enableAutoRouteTracking: false,
      autoTrackPageVisitTime: false,
      enableCorsCorrelation: false,
    })
    expect(sdk.initializers).toEqual([removeReferrer])
  })

  it('removes the referrer from telemetry items', () => {
    const item = { baseData: { name: '/players', refUri: 'https://app.example/players?q=private_secret' } }
    expect(removeReferrer(item)).toBe(true)
    expect(item.baseData).toEqual({ name: '/players' })
    expect(removeReferrer({})).toBe(true)
  })
})
