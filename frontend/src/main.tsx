import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { parseLogLevel } from './logging/domain'
import { createBrowserLogger } from './logging/logger'
import { createGlobalDiagnostics, diagnosticRootOptions } from './logging/lifecycle'
import { activateDiagnostics, browserDiagnostics } from './logging/runtime'
import { activatePageViews, createApplicationInsightsClient, createPageViewTracker, createTelemetrySink } from './logging/telemetry'
import './styles.css'

const connectionString = import.meta.env.VITE_APPINSIGHTS_CONNECTION_STRING?.trim()
const telemetry = connectionString ? createApplicationInsightsClient(connectionString) : undefined
const deactivate = activateDiagnostics(createBrowserLogger({ level: parseLogLevel(import.meta.env.VITE_LOG_LEVEL), environment: import.meta.env.APP_ENV, telemetry: telemetry && createTelemetrySink(telemetry) }))
const deactivatePageViews = telemetry ? activatePageViews(createPageViewTracker(telemetry, window.location.origin)) : () => {}
const globalDiagnostics = createGlobalDiagnostics(window, browserDiagnostics)
globalDiagnostics.start()
browserDiagnostics.emit({ event: 'app.started', component: 'app', severity: 'INFO' })
const root = createRoot(document.getElementById('root')!, diagnosticRootOptions(browserDiagnostics))
root.render(<StrictMode><ErrorBoundary><App /></ErrorBoundary></StrictMode>)
import.meta.hot?.dispose(() => { root.unmount(); globalDiagnostics.stop(); deactivate(); deactivatePageViews() })
