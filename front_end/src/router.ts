import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

// Hash history so the SPA works when served as static files by FastAPI without
// needing server-side fallback routing.
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('./pages/HomePage.vue') },
  { path: '/project', name: 'project', component: () => import('./pages/ProjectCreatePage.vue') },
  { path: '/console', name: 'console', component: () => import('./pages/CameraConsolePage.vue') },
  { path: '/annotate', name: 'annotate', component: () => import('./pages/SnapshotEditorPage.vue') },
  { path: '/reports', name: 'reports', component: () => import('./pages/ReportCenterPage.vue') },
  { path: '/reports/:id', name: 'report-detail', component: () => import('./pages/ReportDetailPage.vue'), props: true },
  { path: '/settings', name: 'settings', component: () => import('./pages/SettingsPage.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes
})
