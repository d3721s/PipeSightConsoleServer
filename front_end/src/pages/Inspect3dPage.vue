<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvButton } from '@carbon/vue'
import { Camera24, ChevronLeft24, CubeView24, Image24, Report24, ZoomIn24, ZoomOut24 } from '@carbon/icons-vue'
import PointCloudViewer from '../components/PointCloudViewer.vue'
import DepthMapViewer from '../components/DepthMapViewer.vue'
import OsdOverlay from '../components/OsdOverlay.vue'
import { api } from '../api'
import { leftWheelM, rightWheelM } from '../stores/odometer'
import { activeReport, currentProject, currentSession, notify, reportToggling, toggleReport } from '../stores/session'
import { formatWheelMileage } from '../utils/osd'

const router = useRouter()

type ViewMode = 'pointcloud' | 'depth'
type ViewerHandle = {
  snapshot: () => string
  zoomBy?: (factor: number) => void
}

const mode = ref<ViewMode>('pointcloud')
const modeLabel = computed(() => (mode.value === 'pointcloud' ? '点云' : '深度图'))
const viewerComponent = computed(() => (mode.value === 'pointcloud' ? PointCloudViewer : DepthMapViewer))

// Connect directly to the C++ bridge for the live stream; backend API still
// handles snapshots and other app calls.
const bridgeWsUrl = computed(() => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const port = mode.value === 'pointcloud' ? 9090 : 9091
  return `${protocol}://${location.hostname}:${port}`
})

const viewer = ref<ViewerHandle | null>(null)
const videoArea = ref<HTMLDivElement | null>(null)
const DEFAULT_POINTCLOUD_ZOOM = 1.2
const MIN_POINTCLOUD_ZOOM = 0.2
const MAX_POINTCLOUD_ZOOM = 8
const zoomLabel = ref(`${DEFAULT_POINTCLOUD_ZOOM.toFixed(1)}x`)

function setMode(next: ViewMode) {
  if (mode.value === next) return
  mode.value = next
  viewer.value = null
  updateZoomLabel(DEFAULT_POINTCLOUD_ZOOM)
}

function nudgeZoom(dir: number) {
  if (mode.value !== 'pointcloud') return
  // dir>0 zoom in (camera dolly closer), dir<0 zoom out.
  viewer.value?.zoomBy?.(dir > 0 ? 0.8 : 1.25)
}

function updateZoomLabel(value: number) {
  const zoom = Math.max(MIN_POINTCLOUD_ZOOM, Math.min(MAX_POINTCLOUD_ZOOM, value))
  zoomLabel.value = `${zoom.toFixed(1)}x`
}

async function capture3d() {
  const dataUrl = viewer.value?.snapshot()
  if (!dataUrl) {
    notify(`${modeLabel.value}画面未就绪`, 'warning')
    return
  }
  try {
    const image = await addOsdToSnapshot(dataUrl)
    const asset = await api.imageSnapshot({
      projectId: currentProject.value?.id,
      sessionId: currentSession.value?.id,
      leftMileage: leftWheelM.value,
      rightMileage: rightWheelM.value,
      image,
      source: mode.value === 'depth' ? 'depth' : '3d'
    })
    notify(`${modeLabel.value}拍照已保存 #${(asset as { id?: number }).id ?? ''}`, 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

function loadSnapshotImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('截图图像加载失败'))
    image.src = dataUrl
  })
}

async function addOsdToSnapshot(dataUrl: string): Promise<string> {
  const image = await loadSnapshotImage(dataUrl)
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight

  const ctx = canvas.getContext('2d')
  if (!ctx) return dataUrl

  ctx.drawImage(image, 0, 0)
  drawSnapshotOsd(ctx, canvas.width, canvas.height)
  return canvas.toDataURL('image/png')
}

function drawSnapshotOsd(ctx: CanvasRenderingContext2D, width: number, height: number) {
  const metrics = getSnapshotOsdMetrics(width, height)
  const lines = [
    `时间：${new Date().toLocaleString()}`,
    `距离：${formatWheelMileage(leftWheelM.value, rightWheelM.value)}`,
    `项目名称：${currentProject.value?.name || '未创建项目'}`,
    `地点：${currentProject.value?.location || '-'}`
  ]

  ctx.save()
  const { borderWidth, fontSize, lineHeight, paddingX, paddingY, x, y } = metrics
  ctx.font = `${fontSize}px "IBM Plex Sans", "Microsoft YaHei", "Segoe UI", sans-serif`
  const textWidth = Math.max(...lines.map(line => ctx.measureText(line).width))
  const boxWidth = Math.ceil(borderWidth + paddingX * 2 + textWidth)
  const boxHeight = paddingY * 2 + lineHeight * lines.length

  ctx.fillStyle = 'rgba(0, 0, 0, 0.45)'
  ctx.fillRect(x, y, boxWidth, boxHeight)
  ctx.fillStyle = '#0f62fe'
  ctx.fillRect(x, y, borderWidth, boxHeight)

  ctx.fillStyle = '#f4f4f4'
  ctx.shadowColor = 'rgba(0, 0, 0, 0.8)'
  ctx.shadowBlur = Math.max(2, Math.round(fontSize * 0.08))
  ctx.shadowOffsetY = Math.max(1, Math.round(fontSize * 0.06))
  ctx.textBaseline = 'top'
  const textX = x + borderWidth + paddingX
  let textY = y + paddingY
  for (const line of lines) {
    ctx.fillText(line, textX, textY)
    textY += lineHeight
  }
  ctx.restore()
}

function getSnapshotOsdMetrics(width: number, height: number) {
  const fallbackMargin = Math.max(20, Math.round(Math.min(width, height) * 0.025))
  const fallbackFontSize = Math.max(22, Math.round(Math.min(width, height) * 0.028))
  const fallbackLineHeight = Math.round(fallbackFontSize * 1.45)
  const fallbackPaddingX = Math.round(fallbackMargin * 0.75)
  const fallbackPaddingY = Math.round(fallbackMargin * 0.5)
  const fallbackBorderWidth = Math.max(3, Math.round(fallbackMargin * 0.12))

  const area = videoArea.value
  const osd = area?.querySelector<HTMLElement>('.osd-overlay')
  if (!area || !osd) {
    return {
      x: fallbackMargin,
      y: fallbackMargin,
      borderWidth: fallbackBorderWidth,
      fontSize: fallbackFontSize,
      lineHeight: fallbackLineHeight,
      paddingX: fallbackPaddingX,
      paddingY: fallbackPaddingY
    }
  }

  const areaRect = area.getBoundingClientRect()
  const osdRect = osd.getBoundingClientRect()
  if (areaRect.width <= 0 || areaRect.height <= 0) {
    return {
      x: fallbackMargin,
      y: fallbackMargin,
      borderWidth: fallbackBorderWidth,
      fontSize: fallbackFontSize,
      lineHeight: fallbackLineHeight,
      paddingX: fallbackPaddingX,
      paddingY: fallbackPaddingY
    }
  }

  const style = window.getComputedStyle(osd)
  const scaleX = width / areaRect.width
  const scaleY = height / areaRect.height
  const scale = Math.min(scaleX, scaleY)
  return {
    x: Math.round((osdRect.left - areaRect.left) * scaleX),
    y: Math.round((osdRect.top - areaRect.top) * scaleY),
    borderWidth: Math.max(1, Math.round(parsePx(style.borderLeftWidth, 3) * scaleX)),
    fontSize: Math.max(1, Math.round(parsePx(style.fontSize, 13) * scale)),
    lineHeight: Math.max(1, Math.round(parsePx(style.lineHeight, 19) * scale)),
    paddingX: Math.max(0, Math.round(parsePx(style.paddingLeft, 12) * scaleX)),
    paddingY: Math.max(0, Math.round(parsePx(style.paddingTop, 8) * scaleY))
  }
}

function parsePx(value: string, fallback: number) {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : fallback
}
</script>

<template>
  <div class="console-page">
    <div ref="videoArea" class="video-area">
      <component :is="viewerComponent" :key="mode" ref="viewer" :ws-url="bridgeWsUrl" @zoom-change="updateZoomLabel" />

      <osd-overlay
        :left-mileage="leftWheelM"
        :right-mileage="rightWheelM"
        :project-name="currentProject?.name || ''"
        :location="currentProject?.location || ''"
      />

      <div v-if="mode === 'pointcloud'" class="zoom-cluster">
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
          :disabled="reportToggling"
          @click="toggleReport"
        >{{ reportToggling ? '处理中' : activeReport ? '停止报告' : '开启报告' }}</cv-button>
      </div>

      <div class="rail-section">
        <span class="rail-label">显示</span>
        <div class="mode-switch">
          <cv-button
            class="mode-btn"
            size="sm"
            :kind="mode === 'pointcloud' ? 'secondary' : 'ghost'"
            :icon="CubeView24"
            :aria-pressed="mode === 'pointcloud'"
            @click="setMode('pointcloud')"
          >点云</cv-button>
          <cv-button
            class="mode-btn"
            size="sm"
            :kind="mode === 'depth' ? 'secondary' : 'ghost'"
            :icon="Image24"
            :aria-pressed="mode === 'depth'"
            @click="setMode('depth')"
          >深度图</cv-button>
        </div>
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
.mode-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}
.mode-btn {
  width: 100%;
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
