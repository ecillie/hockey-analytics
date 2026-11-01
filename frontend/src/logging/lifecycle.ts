import type { RootOptions } from 'react-dom/client'
import type { BrowserDiagnostics } from './domain'
import { isExpectedAbort } from './format'

export function createGlobalDiagnostics(target: Window, diagnostics: BrowserDiagnostics) {
  let started = false
  function onError(event: ErrorEvent) {
    event.preventDefault()
    diagnostics.report(event.error, { event: 'global.error', component: 'global', severity: 'ERROR', category: 'unhandled' })
  }
  function onRejection(event: PromiseRejectionEvent) {
    event.preventDefault()
    if (isExpectedAbort(event.reason)) return
    diagnostics.report(event.reason, { event: 'global.unhandled_rejection', component: 'global', severity: 'ERROR', category: 'unhandled' })
  }
  return Object.freeze({
    start() {
      if (started) return
      started = true
      target.addEventListener('error', onError)
      target.addEventListener('unhandledrejection', onRejection)
    },
    stop() {
      if (!started) return
      started = false
      target.removeEventListener('error', onError)
      target.removeEventListener('unhandledrejection', onRejection)
    },
  })
}

export function diagnosticRootOptions(diagnostics: BrowserDiagnostics): RootOptions {
  return {
    onCaughtError(error) { diagnostics.report(error, { event: 'react.render_failed', component: 'react', severity: 'ERROR', category: 'render' }) },
    onUncaughtError(error) { diagnostics.report(error, { event: 'react.uncaught_error', component: 'react', severity: 'CRITICAL', category: 'render' }) },
    onRecoverableError(error) { diagnostics.report(error, { event: 'react.recovered_error', component: 'react', severity: 'WARNING', category: 'render' }) },
  }
}
