import type { BrowserDiagnostics, Diagnostic } from './domain'

let active: BrowserDiagnostics | undefined

export const browserDiagnostics: BrowserDiagnostics = Object.freeze({
  emit(entry: Diagnostic) { try { active?.emit(entry) } catch { return } },
  report(error: unknown, entry: Diagnostic) { try { active?.report(error, entry) } catch { return } },
})

export function activateDiagnostics(diagnostics: BrowserDiagnostics): () => void {
  if (active !== undefined) throw new Error('Browser diagnostics already have an owner.')
  active = diagnostics
  let stopped = false
  return () => {
    if (stopped) return
    stopped = true
    active = undefined
  }
}
