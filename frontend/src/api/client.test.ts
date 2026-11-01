import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError } from './client'
import { createBrowserLogger } from '../logging/logger'

function observedClient(baseUrl = 'https://stats.example') {
  const write = vi.fn()
  const diagnostics = createBrowserLogger({ level: 'DEBUG', sink: { write } })
  return { client: new ApiClient(baseUrl, diagnostics), diagnostics, write, records: () => write.mock.calls.map(([, text]) => JSON.parse(text)) }
}

describe('ApiClient', () => {
  afterEach(() => vi.restoreAllMocks())

  it('serializes query parameters and parses JSON', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'content-type': 'application/json' } }))
    const client = new ApiClient('https://stats.example')
    await expect(client.get('/api/health', { season: 2025, ids: [1, 2] })).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(new URL('https://stats.example/api/health?season=2025&ids=1%2C2'), expect.objectContaining({ method: 'GET' }))
  })

  it('normalizes backend errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code: 'PLAYER_NOT_FOUND', message: 'Player not found.' } }), { status: 404, headers: { 'content-type': 'application/json' } }))
    const promise = new ApiClient('https://stats.example').get('/api/players/0')
    await expect(promise).rejects.toMatchObject({ status: 404, code: 'PLAYER_NOT_FOUND', message: 'Player not found.' } satisfies Partial<ApiError>)
  })

  it('normalizes network failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
  })

  it('skips empty query values and forwards boolean and scalar values', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'content-type': 'application/json' } }))
    const controller = new AbortController()
    await new ApiClient('https://stats.example/').get('/api/test', { empty: '', missing: undefined, nil: null, active: false, page: 2 }, controller.signal)
    expect(fetchMock).toHaveBeenCalledWith(new URL('https://stats.example/api/test?active=false&page=2'), expect.objectContaining({ signal: controller.signal }))
  })

  it('preserves abort failures', async () => {
    const abort = new DOMException('Aborted', 'AbortError')
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(abort)
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toBe(abort)
  })

  it('rejects non-JSON success responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } }))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ status: 200, code: 'INVALID_RESPONSE' })
  })

  it('rejects responses without a content type', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('supplies fallback fields for non-JSON API errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('failure', { status: 503, headers: { 'content-type': 'text/plain' } }))
    await expect(new ApiClient('https://stats.example').get('/api/health')).rejects.toMatchObject({ status: 503, code: 'HTTP_503', message: 'The API could not complete this request.' })
  })

  it('retains structured validation details', async () => {
    const details = { season: ['is invalid'] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { code: 'VALIDATION', message: 'Invalid request.', details } }), { status: 422, headers: { 'content-type': 'application/json' } }))
    await expect(new ApiClient('https://stats.example').get('/api/players')).rejects.toMatchObject({ details })
  })

  it('correlates safe route templates with the server request ID without logging queries or response bodies', async () => {
    const requestId = 'a'.repeat(32)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ secret: 'private payload' }), { headers: { 'content-type': 'application/json', 'x-request-id': requestId } }))
    const observed = observedClient()
    await expect(observed.client.get('/api/players/123/stats', { search: 'private search' })).resolves.toEqual({ secret: 'private payload' })
    expect(observed.records()).toMatchObject([
      { event: 'api.request_started', severity: 'DEBUG', route: '/api/players/{id}/stats' },
      { event: 'api.request_finished', severity: 'DEBUG', route: '/api/players/{id}/stats', status: 200, request_id: requestId },
    ])
    expect(observed.records()[1].duration_ms).toBeGreaterThanOrEqual(0)
    expect(JSON.stringify(observed.records())).not.toContain('private')
  })

  it('preserves handled API error fields and emits one safe diagnostic shared with global handlers', async () => {
    const requestId = 'b'.repeat(32)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ error: { message: 'private message', code: 'private code', details: { token: ['private details'] } } }), { status: 422, headers: { 'content-type': 'application/json', 'x-request-id': requestId } }))
    const observed = observedClient()
    const failure = await observed.client.get('/api/players/123').catch((error: unknown) => error)
    expect(failure).toMatchObject({ message: 'private message', code: 'private code', details: { token: ['private details'] }, requestId })
    observed.diagnostics.report(failure, { event: 'global.unhandled_rejection', component: 'global', severity: 'ERROR' })
    expect(observed.records()).toHaveLength(2)
    expect(observed.records()[1]).toMatchObject({ event: 'api.request_failed', severity: 'ERROR', category: 'http', route: '/api/players/{id}', request_id: requestId, status: 422 })
    expect(JSON.stringify(observed.records())).not.toContain('private')
  })

  it('normalizes network errors without serializing their exception data', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('private URL and token'))
    const observed = observedClient()
    await expect(observed.client.get('/api/search', { q: 'private query' })).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
    expect(observed.records()[1]).toMatchObject({ category: 'network', status: 0 })
    expect(JSON.stringify(observed.records())).not.toContain('private')
  })

  it('preserves JSON decoding exceptions and drops malformed correlation headers', async () => {
    const response = new Response('private malformed JSON', { headers: { 'content-type': 'application/json', 'x-request-id': 'private header' } })
    const failure = new SyntaxError('private parse details')
    vi.spyOn(response, 'json').mockRejectedValue(failure)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response)
    const observed = observedClient()
    await expect(observed.client.get('/api/health')).rejects.toBe(failure)
    expect(observed.records()[1]).toMatchObject({ category: 'decode', status: 200 })
    expect(observed.records()[1]).not.toHaveProperty('request_id')
    expect(JSON.stringify(observed.records())).not.toContain('private')
  })

  it('reports non-JSON success responses as invalid without recording their contents', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('private page', { headers: { 'content-type': 'text/html' } }))
    const observed = observedClient()
    await expect(observed.client.get('/api/health')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    expect(observed.records()[1]).toMatchObject({ category: 'invalid_response', status: 200 })
    expect(JSON.stringify(observed.records())).not.toContain('private')
  })

  it.each([new DOMException('private cancellation', 'AbortError'), Object.assign(new Error('private cancellation'), { name: 'AbortError' })])('keeps expected aborts at DEBUG and preserves identity', async (failure) => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(failure)
    const observed = observedClient()
    await expect(observed.client.get('/api/health')).rejects.toBe(failure)
    expect(observed.records()[1]).toMatchObject({ event: 'api.request_cancelled', severity: 'DEBUG' })
    expect(observed.records().some((record) => record.severity === 'ERROR')).toBe(false)
  })

  it('preserves arbitrary abort reasons when the caller cancels', async () => {
    const controller = new AbortController()
    controller.abort('private abort reason')
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(controller.signal.reason)
    const observed = observedClient()
    await expect(observed.client.get('/api/health', undefined, controller.signal)).rejects.toBe(controller.signal.reason)
    expect(observed.records()[1].event).toBe('api.request_cancelled')
  })

  it('treats a response-body cancellation as quiet cancellation', async () => {
    const failure = new DOMException('private abort', 'AbortError')
    const response = new Response(null, { headers: { 'content-type': 'application/json' } })
    vi.spyOn(response, 'json').mockRejectedValue(failure)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response)
    const observed = observedClient()
    await expect(observed.client.get('/api/health')).rejects.toBe(failure)
    expect(observed.records()[1]).toMatchObject({ event: 'api.request_cancelled', status: 200 })
  })

  it('reports invalid URL construction without logging the URL or changing the exception', async () => {
    const observed = observedClient('private invalid URL')
    await expect(observed.client.get('/api/health')).rejects.toBeInstanceOf(TypeError)
    expect(observed.records()).toMatchObject([{ category: 'unexpected', event: 'api.request_failed' }])
    expect(JSON.stringify(observed.records())).not.toContain('private')
  })

  it('contains diagnostic and clock failures without changing success or failure results', async () => {
    vi.spyOn(performance, 'now').mockImplementation(() => { throw new Error('clock unavailable') })
    const client = new ApiClient('https://stats.example', { emit() { throw new Error('sink') }, report() { throw new Error('sink') } })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { headers: { 'content-type': 'application/json' } }))
    await expect(client.get('/api/health')).resolves.toEqual({})
    fetchMock.mockRejectedValue(new Error('private network details'))
    await expect(client.get('/api/health')).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
  })

  it('keeps normal successes and expected cancellations silent at INFO', async () => {
    const write = vi.fn()
    const client = new ApiClient('https://stats.example', createBrowserLogger({ sink: { write } }))
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { headers: { 'content-type': 'application/json' } }))
    await expect(client.get('/api/health')).resolves.toEqual({})
    fetchMock.mockRejectedValue(new DOMException('Aborted', 'AbortError'))
    await expect(client.get('/api/health')).rejects.toBeInstanceOf(DOMException)
    expect(write).not.toHaveBeenCalled()
  })
})
