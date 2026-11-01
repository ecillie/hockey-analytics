import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { createGlobalDiagnostics, diagnosticRootOptions } from './lifecycle'
import { createBrowserLogger } from './logger'

afterEach(() => vi.restoreAllMocks())

function rejection(reason: unknown) {
  const event = new Event('unhandledrejection', { cancelable: true })
  Object.defineProperty(event, 'reason', { value: reason })
  return event
}

describe('browser lifecycle diagnostics', () => {
  it('owns exactly two listeners and supports idempotent cleanup and restart', () => {
    const write = vi.fn()
    const logger = createBrowserLogger({ sink: { write } })
    const handlers = createGlobalDiagnostics(window, logger)
    const add = vi.spyOn(window, 'addEventListener')
    const remove = vi.spyOn(window, 'removeEventListener')
    const other = vi.fn()
    window.addEventListener('error', other)
    handlers.stop()
    handlers.start()
    handlers.start()
    const error = new Error('private token')
    const event = new ErrorEvent('error', { error, message: 'private token', cancelable: true })
    window.dispatchEvent(event)
    const duplicate = rejection(error)
    window.dispatchEvent(duplicate)
    expect(event.defaultPrevented).toBe(true)
    expect(duplicate.defaultPrevented).toBe(true)
    expect(other).toHaveBeenCalledTimes(1)
    expect(write).toHaveBeenCalledTimes(1)
    expect(write.mock.calls[0][1]).not.toContain('private token')
    window.dispatchEvent(rejection(new DOMException('private', 'AbortError')))
    expect(write).toHaveBeenCalledTimes(1)
    handlers.stop()
    handlers.stop()
    window.dispatchEvent(rejection(new Error('after stop')))
    expect(write).toHaveBeenCalledTimes(1)
    handlers.start()
    window.dispatchEvent(rejection('private reason'))
    expect(write).toHaveBeenCalledTimes(2)
    handlers.stop()
    expect(add.mock.calls.filter(([name]) => name === 'unhandledrejection')).toHaveLength(2)
    expect(remove.mock.calls.filter(([name]) => name === 'unhandledrejection')).toHaveLength(2)
    window.removeEventListener('error', other)
  })

  it('renders a generic fallback and reports once under StrictMode without raw React console output', async () => {
    const write = vi.fn()
    const raw = vi.spyOn(console, 'error').mockImplementation(() => {})
    const error = new Error('private render token')
    const logger = createBrowserLogger({ sink: { write } })
    const container = document.createElement('div')
    const root = createRoot(container, diagnosticRootOptions(logger))
    function Broken(): never { throw error }
    try {
      await act(async () => { root.render(<StrictMode><ErrorBoundary><Broken /></ErrorBoundary></StrictMode>) })
      expect(container.querySelector('[role="alert"]')).toHaveTextContent('Something went wrong')
      expect(container.querySelector('a')).toHaveAttribute('href', '/')
      expect(container.textContent).not.toContain('private')
      expect(write).toHaveBeenCalledTimes(1)
      expect(JSON.parse(write.mock.calls[0][1])).toMatchObject({ event: 'react.render_failed', severity: 'ERROR' })
      expect(raw).not.toHaveBeenCalled()
      logger.report(error, { event: 'global.error', severity: 'ERROR', component: 'global' })
      expect(write).toHaveBeenCalledTimes(1)
    } finally { await act(async () => root.unmount()) }
  })

  it('keeps healthy children visible and reports uncaught and recoverable root errors at their severities', async () => {
    const write = vi.fn()
    const logger = createBrowserLogger({ sink: { write } })
    const options = diagnosticRootOptions(logger)
    const container = document.createElement('div')
    const root = createRoot(container, options)
    try {
      await act(async () => root.render(<ErrorBoundary><p>Healthy</p></ErrorBoundary>))
      expect(container.textContent).toBe('Healthy')
      options.onUncaughtError?.(new Error('private uncaught'), { componentStack: 'private stack' })
      options.onRecoverableError?.(new Error('private recovery'), { componentStack: 'private stack' })
      expect(write.mock.calls.map(([severity]) => severity)).toEqual(['CRITICAL', 'WARNING'])
      expect(JSON.stringify(write.mock.calls)).not.toContain('private')
    } finally { await act(async () => root.unmount()) }
  })
})
