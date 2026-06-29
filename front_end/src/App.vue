<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CvHeader, CvHeaderName, CvHeaderNav, CvHeaderMenuItem, CvContent } from '@carbon/vue'
import { ExpandScreen24, ShrinkScreen24 } from '@carbon/icons-vue'
import { cameraControlSocket } from './ws'
import { ensureLoaded } from './stores/cameras'
import { startOdometerPolling } from './stores/odometer'
import { activeReport, restoreSession } from './stores/session'
import AppToast from './components/AppToast.vue'
import CameraConsolePage from './pages/CameraConsolePage.vue'

const route = useRoute()
const router = useRouter()
const isFullscreen = ref(false)

interface NavItem {
  name: string
  label: string
  to: string
}
const navItems: NavItem[] = [
  { name: 'home', label: '首页', to: '/' },
  { name: 'project', label: '项目', to: '/project' },
  { name: 'console', label: '实时巡检', to: '/console' },
  { name: 'inspect3d', label: '三维巡检', to: '/inspect3d' },
  { name: 'annotate', label: '标注', to: '/annotate' },
  { name: 'reports', label: '报告', to: '/reports' },
  { name: 'settings', label: '设置', to: '/settings' }
]

const activeName = computed(() => {
  // report-detail highlights the 报告 tab.
  return route.name === 'report-detail' ? 'reports' : route.name
})

const isConsoleRoute = computed(() => route.name === 'console')
const isFullBleedRoute = computed(() => route.name === 'console' || route.name === 'inspect3d')
const consoleMounted = ref(isConsoleRoute.value)

watch(isConsoleRoute, (active) => {
  if (active) consoleMounted.value = true
}, { immediate: true })

function go(item: NavItem) {
  if (route.path !== item.to) router.push(item.to)
}

function syncFullscreen() {
  isFullscreen.value = document.fullscreenElement !== null
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else {
      await document.documentElement.requestFullscreen()
    }
  } catch {
    syncFullscreen()
  }
}

onMounted(() => {
  document.addEventListener('fullscreenchange', syncFullscreen)
  syncFullscreen()
  cameraControlSocket.connect()
  startOdometerPolling()
  ensureLoaded().catch(() => undefined)
  // Re-hydrate the current project/session + running report after a page reload.
  restoreSession().catch(() => undefined)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreen)
})
</script>

<template>
  <div class="app-shell">
    <cv-header aria-label="PipeSight">
      <cv-header-name prefix="PipeSight">风电叶片内腔巡检系统</cv-header-name>
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
      <button
        type="button"
        class="bx--header__action app-fullscreen-toggle"
        :aria-label="isFullscreen ? '退出全屏' : '进入全屏'"
        :title="isFullscreen ? '退出全屏' : '进入全屏'"
        @click="toggleFullscreen"
      >
        <component :is="isFullscreen ? ShrinkScreen24 : ExpandScreen24" />
      </button>
    </cv-header>

    <cv-content class="app-content" :class="{ 'app-content--fullbleed': isFullBleedRoute }">
      <!-- Keep the console mounted in the real DOM once visited. Android Chrome
           can stall WebRTC if Vue keep-alive detaches the video element. -->
      <camera-console-page
        v-if="consoleMounted"
        class="persistent-console"
        :class="{ 'is-active': isConsoleRoute }"
        :active="isConsoleRoute"
      />
      <div v-if="!isConsoleRoute" class="route-content">
        <router-view />
      </div>
    </cv-content>

    <app-toast />
  </div>
</template>
