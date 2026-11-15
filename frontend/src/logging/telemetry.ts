import { ApplicationInsights } from '@microsoft/applicationinsights-web'
import type { LogLevel } from './domain'

export type TelemetryPayload = Readonly<Record<string, string | number | boolean>>

export interface TelemetrySink {
  write(severity: LogLevel, payload: TelemetryPayload): void
}

export interface PageViewTracker {
  track(pathname: string): void
}

export interface TelemetryClient {
  trackTrace(trace: { message: string; severityLevel: number }, properties: TelemetryPayload): void
  trackException(exception: { exception: Error; severityLevel: number }, properties: TelemetryPayload): void
  trackPageView(pageView: { name: string; uri: string }): void
}

type TelemetryItem = { baseData?: Record<string, unknown> }

// Application Insights SeverityLevel: Verbose, Information, Warning, Error, Critical.
const severityLevels: Readonly<Record<LogLevel, number>> = Object.freeze({ DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 })
const exceptionEvents: readonly string[] = ['react.render_failed', 'react.uncaught_error', 'react.recovered_error', 'global.error', 'global.unhandled_rejection']
const pagePatterns: ReadonlyArray<readonly [RegExp, string]> = [
  [/^\/$/, '/'],
  [/^\/players\/?$/, '/players'],
  [/^\/players\/[^/]+\/?$/, '/players/{id}'],
  [/^\/teams\/?$/, '/teams'],
  [/^\/teams\/[^/]+\/?$/, '/teams/{id}'],
  [/^\/compare\/?$/, '/compare'],
  [/^\/about\/?$/, '/about'],
  [/^\/future-plans\/?$/, '/future-plans'],
]

export function readPagePattern(pathname: string): string {
  return pagePatterns.find(([pattern]) => pattern.test(pathname))?.[1] ?? 'unknown'
}

export function createTelemetrySink(client: TelemetryClient): TelemetrySink {
  return Object.freeze({
    write(severity: LogLevel, payload: TelemetryPayload) {
      const severityLevel = severityLevels[severity]
      const message = String(payload.message)
      if (exceptionEvents.includes(String(payload.event))) {
        const exception = Object.assign(new Error(message), { name: String(payload.event), stack: undefined })
        client.trackException({ exception, severityLevel }, payload)
      } else client.trackTrace({ message, severityLevel }, payload)
    },
  })
}

export function createPageViewTracker(client: TelemetryClient, origin: string): PageViewTracker {
  return Object.freeze({
    track(pathname: string) {
      try {
        const name = readPagePattern(pathname)
        client.trackPageView({ name, uri: `${origin}${name === 'unknown' ? '/unknown' : name}` })
      } catch { return }
    },
  })
}

// The SDK fills refUri from document.referrer, which can carry query strings.
export function removeReferrer(item: TelemetryItem): boolean {
  if (item.baseData !== undefined) delete item.baseData.refUri
  return true
}

export function createApplicationInsightsClient(connectionString: string): TelemetryClient {
  const insights = new ApplicationInsights({
    config: {
      connectionString,
      disableCookiesUsage: true,
      enableSessionStorageBuffer: false,
      disableAjaxTracking: true,
      disableFetchTracking: true,
      disableExceptionTracking: true,
      enableUnhandledPromiseRejectionTracking: false,
      enableAutoRouteTracking: false,
      autoTrackPageVisitTime: false,
      enableCorsCorrelation: false,
    },
  })
  insights.loadAppInsights()
  insights.addTelemetryInitializer(removeReferrer)
  return insights
}

let activePageViews: PageViewTracker | undefined

export const browserPageViews: PageViewTracker = Object.freeze({
  track(pathname: string) { try { activePageViews?.track(pathname) } catch { return } },
})

export function activatePageViews(tracker: PageViewTracker): () => void {
  if (activePageViews !== undefined) throw new Error('Page views already have an owner.')
  activePageViews = tracker
  let stopped = false
  return () => {
    if (stopped) return
    stopped = true
    activePageViews = undefined
  }
}
