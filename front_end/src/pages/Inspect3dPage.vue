<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvButton } from '@carbon/vue'
import { Camera24, ZoomIn24, ZoomOut24, Report24, ChevronLeft24 } from '@carbon/icons-vue'
import PointCloudViewer from '../components/PointCloudViewer.vue'
import OsdOverlay from '../components/OsdOverlay.vue'
import { api } from '../api'
import { distance } from '../stores/odometer'
import { activeReport, currentProject, currentSession, notify, toggleReport } from '../stores/session'

const router = useRouter()

// Use the backend proxy so the browser only needs to reach the main app port.
const bridgeWsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/pointcloud`

const viewer = ref<InstanceType<typeof PointCloudViewer> | null>(null)
const zoomLabel = ref('1.0x')
let zoomFactor = 1

function nudgeZoom(dir: number) {
  // dir>0 zoom in (camera dolly closer), dir<0 zoom out.
  viewer.value?.zoomBy(dir > 0 ? 0.8 : 1.25)
  zoomFactor = Math.max(0.2, Math.min(8, zoomFactor * (dir > 0 ? 1.25 : 0.8)))
  zoomLabel.value = `${zoomFactor.toFixed(1)}x`
}

async function capture3d() {
  const dataUrl = viewer.value?.snapshot()
  if (!dataUrl) {
    notify('点云画面未就绪', 'warning')
    return
  }
  try {
    const asset = await api.imageSnapshot({
      projectId: currentProject.value?.id,
      sessionId: currentSession.value?.id,
      distanceM: distance.value,
      image: dataUrl,
      source: '3d'
    })
    notify(`3D 截图已保存 #${(asset as { id?: number }).id ?? ''}`, 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="console-page">
    <div class="video-area">
      <point-cloud-viewer ref="viewer" :ws-url="bridgeWsUrl" />

      <osd-overlay
        :distance="distance"
        :project-name="currentProject?.name || ''"
        :location="currentProject?.location || ''"
      />

      <!-- Bottom-left: zoom cluster (same as console) -->
      <div class="zoom-cluster">
        <cv-button class="bx--btn--icon-only zoom-btn" kind="ghost" size="sm" :icon="ZoomOut24" @click="nudgeZoom(-1)" />
        <span class="zoom-readout">{{ zoomLabel }}</span>
        <cv-button class="bx--btn--icon-only zoom-btn" kind="ghost" size="sm" :icon="ZoomIn24" @click="nudgeZoom(1)" />
      </div>
    </div>

    <aside class="control-rail">
      <div class="rail-top">
        <cv-button kind="ghost" size="sm" :icon="ChevronLeft24" @click="router.push('/')">返回</cv-button>
        <cv-button
          size="sm"
          :kind="activeReport ? 'danger' : 'secondary'"
          :icon="Report24"
          @click="toggleReport"
        >{{ activeReport ? '停止报告' : '开启报告' }}</cv-button>
      </div>

      <div class="rail-section">
        <span class="rail-label">采集</span>
        <cv-button class="rail-action" :icon="Camera24" @click="capture3d">拍照</cv-button>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.console-page {
  display: grid;
  grid-template-columns: 1fr 18rem;
  height: 100%;
  background: #000;
}
.video-area {
  position: relative;
  overflow: hidden;
  background: #000;
}
.zoom-cluster {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  background: rgba(22, 22, 22, 0.7);
  border-radius: 999px;
  padding: 0.25rem 0.5rem;
}
.zoom-readout {
  min-width: 2.5rem;
  text-align: center;
  color: #f4f4f4;
  font-variant-numeric: tabular-nums;
}
.zoom-btn :deep(.bx--btn__icon) {
  width: 1.5rem;
  height: 1.5rem;
}
.zoom-btn :deep(svg),
.zoom-btn:hover :deep(svg),
.zoom-btn:focus :deep(svg) {
  fill: #ffffff;
}
.control-rail {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1rem;
  background: #161616;
  border-left: 1px solid #393939;
  overflow-y: auto;
}
.rail-top {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.rail-top :deep(.cv-button) {
  width: 100%;
}
.rail-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.rail-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.rail-action {
  width: 100%;
}
</style>
