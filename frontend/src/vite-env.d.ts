/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly APP_ENV?: import('./logging/domain').DeploymentEnvironment
  readonly VITE_LOG_LEVEL?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_USE_MOCK_API?: string
  readonly VITE_MOCK_LATENCY_MS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
