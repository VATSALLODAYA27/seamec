import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import { StrictMode, Suspense, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { ApiError } from './api'
import { forgetAll } from './offline'
import App from './App'
import { DarkMode, themeConfig } from './brand'
import './styles.css'

const queries = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  // When the session runs out, drop back to the sign-in page.
  queryCache: new QueryCache({
    onError: (e) => {
      if (e instanceof ApiError && e.status === 401) {
        forgetAll()
        queries.setQueryData(['me'], null)
      }
    },
  }),
})

function readMode() {
  try {
    return localStorage.getItem('maris-mode') === 'dark'
  } catch {
    return false
  }
}

function Root() {
  const [dark, setDark] = useState(readMode)
  useEffect(() => {
    document.documentElement.dataset.mode = dark ? 'dark' : 'light'
    try {
      localStorage.setItem('maris-mode', dark ? 'dark' : 'light')
    } catch {
      // private window: the choice just is not remembered
    }
  }, [dark])
  return (
    <DarkMode.Provider value={{ dark, flip: () => setDark((d) => !d) }}>
      <ConfigProvider theme={themeConfig(dark)}>
        <AntApp>
          <BrowserRouter>
            <Suspense fallback={<Spin fullscreen />}>
              <App />
            </Suspense>
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </DarkMode.Provider>
  )
}

// The service worker keeps the app itself, so a vessel can open it and file reports with no connection.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => undefined))
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queries}>
      <Root />
    </QueryClientProvider>
  </StrictMode>,
)
