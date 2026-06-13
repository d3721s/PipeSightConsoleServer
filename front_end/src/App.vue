<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CvHeader, CvHeaderName, CvHeaderNav, CvHeaderMenuItem, CvContent } from '@carbon/vue'
import { cameraControlSocket } from './ws'
import { ensureLoaded } from './stores/cameras'
import { startOdometerPolling } from './stores/odometer'
import { activeReport } from './stores/session'
import AppToast from './components/AppToast.vue'

const route = useRoute()
const router = useRouter()

interface NavItem {
  name: string
  label: string
  to: string
}
const navItems: NavItem[] = [
  { name: 'home', label: '首页', to: '/' },
  { name: 'project', label: '项目', to: '/project' },
  { name: 'console', label: '控制', to: '/console' },
  { name: 'annotate', label: '标注', to: '/annotate' },
  { name: 'reports', label: '报告', to: '/reports' },
  { name: 'settings', label: '设置', to: '/settings' }
]

const activeName = computed(() => {
  // report-detail highlights the 报告 tab.
  return route.name === 'report-detail' ? 'reports' : route.name
})

function go(item: NavItem) {
  if (route.path !== item.to) router.push(item.to)
}

onMounted(() => {
  cameraControlSocket.connect()
  startOdometerPolling()
  ensureLoaded().catch(() => undefined)
})
</script>

<template>
  <div class="app-shell">
    <cv-header aria-label="PipeSight">
      <cv-header-name prefix="PipeSight">风电叶片内腔巡检</cv-header-name>
      <cv-header-nav aria-label="主导航">
        <cv-header-menu-item
          v-for="item in navItems"
          :key="item.name"
          href="#"
          :active="activeName === item.name"
          @click.prevent="go(item)"
        >
          {{ item.label }}
          <span v-if="item.name === 'reports' && activeReport" class="nav-rec-dot" />
        </cv-header-menu-item>
      </cv-header-nav>
    </cv-header>

    <cv-content class="app-content">
      <!-- keep-alive so the console preview / WebRTC connection survives nav. -->
      <router-view v-slot="{ Component }">
        <keep-alive include="CameraConsolePage">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </cv-content>

    <app-toast />
  </div>
</template>
