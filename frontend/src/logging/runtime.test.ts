import { describe, expect, it, vi } from 'vitest'
import { activateDiagnostics, browserDiagnostics } from './runtime'

const entry = { event: 'app.started', component: 'app', severity: 'INFO' } as const

describe('browser diagnostic ownership', () => {
  it('is silent before activation and after idempotent cleanup', () => {
    browserDiagnostics.emit(entry)
    browserDiagnostics.report(null, entry)
    const diagnostics = { emit: vi.fn(), report: vi.fn() }
    const stop = activateDiagnostics(diagnostics)
    try {
      expect(() => activateDiagnostics(diagnostics)).toThrow('already have an owner')
      browserDiagnostics.emit(entry)
      browserDiagnostics.report(null, entry)
      expect(diagnostics.emit).toHaveBeenCalledExactlyOnceWith(entry)
      expect(diagnostics.report).toHaveBeenCalledExactlyOnceWith(null, entry)
    } finally { stop() }
    const next = activateDiagnostics(diagnostics)
    stop()
    browserDiagnostics.emit(entry)
    next()
    browserDiagnostics.emit(entry)
    expect(diagnostics.emit).toHaveBeenCalledTimes(2)
  })

  it('contains failures from an installed diagnostic provider', () => {
    const stop = activateDiagnostics({ emit() { throw new Error('sink') }, report() { throw new Error('sink') } })
    try {
      expect(() => browserDiagnostics.emit(entry)).not.toThrow()
      expect(() => browserDiagnostics.report(null, entry)).not.toThrow()
    } finally { stop() }
  })
})
