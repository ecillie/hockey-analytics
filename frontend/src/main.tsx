import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { parseLogLevel } from './logging/domain'
import { createBrowserLogger } from './logging/logger'
import { createGlobalDiagnostics, diagnosticRootOptions } from './logging/lifecycle'
import { activateDiagnostics, browserDiagnostics } from './logging/runtime'
import './styles.css'

const deactivate = activateDiagnostics(createBrowserLogger({ level: parseLogLevel(import.meta.env.VITE_LOG_LEVEL), environment: import.meta.env.APP_ENV }))
const globalDiagnostics = createGlobalDiagnostics(window, browserDiagnostics)
globalDiagnostics.start()
browserDiagnostics.emit({ event: 'app.started', component: 'app', severity: 'INFO' })
const root = createRoot(document.getElementById('root')!, diagnosticRootOptions(browserDiagnostics))
root.render(<StrictMode><ErrorBoundary><App /></ErrorBoundary></StrictMode>)
import.meta.hot?.dispose(() => { root.unmount(); globalDiagnostics.stop(); deactivate() })
