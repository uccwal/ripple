import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'events', component: () => import('@/views/EventsView.vue'), meta: { title: '정책 이벤트' } },
    { path: '/new', name: 'new', component: () => import('@/views/NewRunView.vue'), meta: { title: '새 분석' } },
    { path: '/runs', name: 'runs', component: () => import('@/views/RunsView.vue'), meta: { title: '실행 이력' } },
    { path: '/runs/:id', name: 'run', component: () => import('@/views/RunView.vue'), meta: { title: '분석 워크스페이스' } },
    { path: '/portfolios', name: 'portfolios', component: () => import('@/views/PortfoliosView.vue'), meta: { title: '포트폴리오' } },
    { path: '/system', name: 'system', component: () => import('@/views/SystemView.vue'), meta: { title: '컴포넌트·토큰' } },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: '페이지 없음' } },
  ],
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : null
  document.title = title ? `${title} · RIPPLE` : 'RIPPLE'
})
