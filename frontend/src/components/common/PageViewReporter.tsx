import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { browserPageViews } from '../../logging/telemetry'

export function PageViewReporter() {
  const { pathname } = useLocation()
  useEffect(() => { browserPageViews.track(pathname) }, [pathname])
  return null
}
