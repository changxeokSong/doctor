import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { ApiError } from './api/client.ts'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {  // 콜드스타트 버티게 재시도, 단 4xx는 즉시 실패
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
        return failureCount < 10
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10000),
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
