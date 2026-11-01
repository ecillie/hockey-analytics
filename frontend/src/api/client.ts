import type { ApiErrorBody } from './types'
import type { ApiRoute, BrowserDiagnostics, Diagnostic } from '../logging/domain'
import { isExpectedAbort, readRequestId } from '../logging/format'
import { diagnosticRoute } from '../logging/routes'
import { browserDiagnostics } from '../logging/runtime'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly details?: Record<string, string[]>,
    public readonly requestId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

type QueryValue = string | number | boolean | null | undefined | Array<string | number>

export class ApiClient {
  constructor(private readonly baseUrl: string, private readonly diagnostics: BrowserDiagnostics = browserDiagnostics) {}

  async get<T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal): Promise<T> {
    let route: ApiRoute = 'unknown'
    let category: Diagnostic['category'] = 'unexpected'
    let status: number | undefined
    let requestId: string | undefined
    function now() { try { return performance.now() } catch { return 0 } }
    const started = now()
    const emit = (entry: Diagnostic) => { try { this.diagnostics.emit(entry) } catch { return } }
    try {
      route = diagnosticRoute(path)
      const url = new URL(path, this.baseUrl.endsWith('/') ? this.baseUrl : `${this.baseUrl}/`)
      Object.entries(query ?? {}).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return
        url.searchParams.set(key, Array.isArray(value) ? value.join(',') : String(value))
      })
      emit({ event: 'api.request_started', component: 'api', severity: 'DEBUG', route })
      category = 'network'
      const response = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, signal })
      status = response.status
      requestId = readRequestId(response.headers.get('x-request-id'))
      category = 'decode'
      const contentType = response.headers.get('content-type') ?? ''
      const body: unknown = contentType.includes('application/json') ? await response.json() : null
      if (!response.ok) {
        category = 'http'
        const apiBody = body as Partial<ApiErrorBody> | null
        throw new ApiError(
          apiBody?.error?.message ?? 'The API could not complete this request.',
          response.status,
          apiBody?.error?.code ?? `HTTP_${response.status}`,
          apiBody?.error?.details ?? undefined,
          requestId,
        )
      }
      if (!contentType.includes('application/json')) {
        category = 'invalid_response'
        throw new ApiError('The API returned an invalid response.', response.status, 'INVALID_RESPONSE', undefined, requestId)
      }
      emit({ event: 'api.request_finished', component: 'api', severity: 'DEBUG', route, status, requestId, durationMs: now() - started })
      return body as T
    } catch (error) {
      if (signal?.aborted || isExpectedAbort(error)) {
        emit({ event: 'api.request_cancelled', component: 'api', severity: 'DEBUG', route, status, requestId, durationMs: now() - started })
        throw error
      }
      const failure = category === 'network' ? new ApiError('Unable to reach the NHL Statistics API.', 0, 'NETWORK_ERROR') : error
      try { this.diagnostics.report(failure, { event: 'api.request_failed', component: 'api', severity: 'ERROR', category, route, status: category === 'network' ? 0 : status, requestId, durationMs: now() - started }) } catch { /* Diagnostics never replace the request result. */ }
      throw failure
    }
  }
}
