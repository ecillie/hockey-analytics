import { Component, type ReactNode } from 'react'

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (this.state.failed) return <main className="state-box" role="alert"><h1>Something went wrong</h1><p>Please reload the page to try again.</p><a className="button" href="/">Reload TradeValue</a></main>
    return this.props.children
  }
}
