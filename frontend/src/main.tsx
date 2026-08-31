import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 백엔드 콜드스타트(모델 로딩)가 최대 ~80초까지 걸릴 수 있는데(GPU를 다른 데스크톱 앱과 공유해서
      // 매번 다를 수 있음), react-query 기본값(재시도 3번, 짧은 간격)으로는 그 사이 페이지를 열면
      // 재시도를 다 소진하고 포기해버려서 사이드바 데이터·예시 질문이 안 뜨는 채로 남는다. 창을 다시
      // 포커스하면 refetchOnWindowFocus로 우연히 복구되곤 했는데, 그 우연에 기대지 않도록 재시도
      // 자체를 콜드스타트 시간을 버틸 만큼 끈질기게 늘린다.
      retry: 10,
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
