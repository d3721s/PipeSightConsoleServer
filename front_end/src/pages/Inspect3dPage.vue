<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvButton } from '@carbon/vue'
import { Camera24, ChevronLeft24, Report24, ZoomIn24, ZoomOut24 } from '@carbon/icons-vue'
import PointCloudViewer from '../components/PointCloudViewer.vue'
import DepthMapViewer from '../components/DepthMapViewer.vue'
import CameraImageViewer from '../components/CameraImageViewer.vue'
import OsdOverlay from '../components/OsdOverlay.vue'
import Joystick from '../components/Joystick.vue'
import MobileChassisPanel from '../components/MobileChassisPanel.vue'
import { api } from '../api'
import {
  chassisMaxSpeed,
  chassisControlEnabled,
  leftWheelM,
  rightWheelM,
  sendChassisMove,
  setChassisControlEnabled
} from '../stores/odometer'
import { activeReport, currentProject, currentSession, notify, reportToggling, toggleReport } from '../stores/session'
import { formatWheelMileage } from '../utils/osd'

const router = useRouter()

type ViewMode = 'pointcloud' | 'depth' | 'rgb' | 'infrared'
type MeasureResult = { areaM2: number; triangles: number; skipped: number }
type ViewerHandle = {
  snapshot: () => string
  zoomBy?: (factor: number) => void
  measureRect?: (x0: number, y0: number, x1: number, y1: number) => MeasureResult | null
  hasIntrinsics?: () => boolean
}

// Each mode maps to a label and the C++ bridge WebSocket port it streams on.
const MODE_LABELS: Record<ViewMode, string> = {
  pointcloud: '点云图',
  depth: '深度图',
  rgb: 'RGB图',
  infrared: '红外图'
}
const MODE_PORTS: Record<ViewMode, number> = {
  pointcloud: 9090,
  depth: 9091,
  rgb: 9092,
  infrared: 9093
}

const mode = ref<ViewMode>('pointcloud')
const modeLabel = computed(() => MODE_LABELS[mode.value])
const viewerComponent = computed(() => {
  if (mode.value === 'pointcloud') return PointCloudViewer
  if (mode.value === 'depth') return DepthMapViewer
  return CameraImageViewer
})

// Connect directly to the C++ bridge for the live stream; backend API still
// handles snapshots and other app calls.
const bridgeWsUrl = computed(() => {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${location.hostname}:${MODE_PORTS[mode.value]}`
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
  clearMeasurement()
  updateZoomLabel(DEFAULT_POINTCLOUD_ZOOM)
}

function nudgeZoom(dir: number) {
  if (mode.value !== 'pointcloud') return
  // dir>0 zoom in (camera dolly closer), dir<0 zoom out.
  viewer.value?.zoomBy?.(dir > 0 ? 0.8 : 1.25)
}

function onChassisMove(v: { x: number; y: number }) {
  sendChassisMove(v.x, v.y)
}

// --- Depth-image area measurement (drag a rectangle on the depth view) -------
// The drag rectangle is tracked in CSS px relative to the video area; on release
// it is mapped to depth-frame pixel coords (accounting for object-fit: contain
// letterboxing) and handed to the viewer, which sums the real 3D surface area.
const measuring = ref(false) // a drag is in progress
const measureRectPx = ref<{ x: number; y: number; w: number; h: number } | null>(null)
const areaText = ref<string | null>(null)
let dragStart: { x: number; y: number } | null = null

const measureEnabled = computed(() => mode.value === 'depth')

function localPoint(e: PointerEvent) {
  const rect = videoArea.value!.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function onMeasureDown(e: PointerEvent) {
  if (!measureEnabled.value || !videoArea.value) return
  ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  dragStart = localPoint(e)
  measuring.value = true
  areaText.value = null
  measureRectPx.value = { x: dragStart.x, y: dragStart.y, w: 0, h: 0 }
}

function onMeasureMove(e: PointerEvent) {
  if (!measuring.value || !dragStart) return
  const p = localPoint(e)
  measureRectPx.value = {
    x: Math.min(dragStart.x, p.x),
    y: Math.min(dragStart.y, p.y),
    w: Math.abs(p.x - dragStart.x),
    h: Math.abs(p.y - dragStart.y)
  }
}

function onMeasureUp() {
  if (!measuring.value) return
  measuring.value = false
  const rectPx = measureRectPx.value
  dragStart = null
  if (!rectPx || rectPx.w < 4 || rectPx.h < 4) {
    measureRectPx.value = null
    return
  }
  computeArea(rectPx)
}

// Map a CSS-px rectangle over the video area into depth-frame pixel coords and
// run the measurement. The canvas is letterboxed (object-fit: contain) inside
// the area, so we first find the displayed image box, then scale into frame px.
function computeArea(rectPx: { x: number; y: number; w: number; h: number }) {
  const area = videoArea.value
  const canvas = area?.querySelector<HTMLCanvasElement>('canvas')
  const handle = viewer.value
  if (!area || !canvas || !handle?.measureRect) return
  if (handle.hasIntrinsics && !handle.hasIntrinsics()) {
    notify('未获取到相机内参，无法计算面积', 'warning')
    measureRectPx.value = null
    return
  }
  const fw = canvas.width
  const fh = canvas.height
  if (!fw || !fh) return

  // Displayed image box inside the area (object-fit: contain).
  const aRect = area.getBoundingClientRect()
  const scale = Math.min(aRect.width / fw, aRect.height / fh)
  const dispW = fw * scale
  const dispH = fh * scale
  const offX = (aRect.width - dispW) / 2
  const offY = (aRect.height - dispH) / 2

  const toFrame = (px: number, py: number) => ({
    x: Math.round((px - offX) / scale),
    y: Math.round((py - offY) / scale)
  })
  const a = toFrame(rectPx.x, rectPx.y)
  const b = toFrame(rectPx.x + rectPx.w, rectPx.y + rectPx.h)

  const result = handle.measureRect(a.x, a.y, b.x, b.y)
  if (!result || result.triangles === 0) {
    notify('该区域无有效深度，请重新框选', 'warning')
    areaText.value = null
    return
  }
  areaText.value = formatArea(result.areaM2)
}

function formatArea(m2: number): string {
  if (m2 < 0.01) return `${(m2 * 1e4).toFixed(1)} cm²`
  return `${m2.toFixed(4)} m²`
}

function clearMeasurement() {
  measureRectPx.value = null
  areaText.value = null
}

function updateZoomLabel(value: number) {
  const zoom = Math.max(MIN_POINTCLOUD_ZOOM, Math.min(MAX_POINTCLOUD_ZOOM, value))
  zoomLabel.value = `${zoom.toFixed(1)}x`
}

async function capture3d() {
  const dataUrl = viewer.value?.snapshot()
  if (!dataUrl) {
    notify(`${modeLabel.value}画面还没准备好，请稍候再试`, 'warning')
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
    image.onerror = () => reject(new Error('截图处理失败，请重试'))
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
      <component :is="viewerComponent" :key="mode" ref="viewer" :ws-url="bridgeWsUrl" :label="modeLabel" @zoom-change="updateZoomLabel" />

      <osd-overlay
        :left-mileage="leftWheelM"
        :right-mileage="rightWheelM"
        :project-name="currentProject?.name || ''"
        :location="currentProject?.location || ''"
      />

      <!-- Depth-image area measurement: drag a rectangle to measure surface area. -->
      <div
        v-if="measureEnabled"
        class="measure-surface"
        @pointerdown="onMeasureDown"
        @pointermove="onMeasureMove"
        @pointerup="onMeasureUp"
        @pointercancel="onMeasureUp"
      >
        <div
          v-if="measureRectPx"
          class="measure-rect"
          :style="{ left: measureRectPx.x + 'px', top: measureRectPx.y + 'px', width: measureRectPx.w + 'px', height: measureRectPx.h + 'px' }"
        />
      </div>
      <div v-if="measureEnabled" class="measure-panel">
        <span v-if="areaText" class="measure-value">面积 {{ areaText }}</span>
        <span v-else class="measure-hint">框选区域以测量面积</span>
        <cv-button v-if="areaText" kind="ghost" size="sm" @click="clearMeasurement">清除</cv-button>
      </div>

      <div v-if="mode === 'pointcloud'" class="zoom-cluster">
        <cv-button class="bx--btn--icon-only zoom-btn" kind="ghost" size="sm" :icon="ZoomOut24" @click="nudgeZoom(-1)" />
        <span class="zoom-readout">{{ zoomLabel }}</span>
        <cv-button class="bx--btn--icon-only zoom-btn" kind="ghost" size="sm" :icon="ZoomIn24" @click="nudgeZoom(1)" />
      </div>

      <div class="chassis-cluster">
        <joystick :range="chassisMaxSpeed" :disabled="!chassisControlEnabled" @move="onChassisMove" />
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
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'pointcloud' }"
            @click="setMode('pointcloud')"
          >点云</button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'depth' }"
            @click="setMode('depth')"
          >深度</button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'rgb' }"
            @click="setMode('rgb')"
          >RGB</button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'infrared' }"
            @click="setMode('infrared')"
          >红外</button>
        </div>
      </div>

      <div class="rail-section">
        <span class="rail-label">采集</span>
        <cv-button class="rail-action" :icon="Camera24" @click="capture3d">拍照</cv-button>
      </div>

      <div class="rail-section">
        <span class="rail-label">底盘</span>
        <div class="segmented">
          <button
            type="button"
            class="seg-btn"
            :class="{ active: chassisControlEnabled }"
            @click="setChassisControlEnabled(true)"
          >APP</button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: !chassisControlEnabled }"
            @click="setChassisControlEnabled(false)"
          >遥控</button>
        </div>
      </div>

      <mobile-chassis-panel />
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
.chassis-cluster {
  position: absolute;
  left: 1.25rem;
  bottom: 1.25rem;
}
.measure-surface {
  position: absolute;
  inset: 0;
  cursor: crosshair;
  touch-action: none;
}
.measure-rect {
  position: absolute;
  border: 2px solid #f1c21b;
  background: rgba(241, 194, 27, 0.15);
  pointer-events: none;
}
.measure-panel {
  position: absolute;
  top: 1.25rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: rgba(22, 22, 22, 0.78);
  border-radius: 4px;
  padding: 0.35rem 0.75rem;
  pointer-events: auto;
}
.measure-value {
  color: #f1c21b;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.measure-hint {
  color: #c6c6c6;
  font-size: 0.85rem;
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
/* Segmented 2×2 mode picker — same look as the 前/后摄·云台/固定 toggles. */
.mode-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border: 1px solid #4d4d4d;
  border-radius: 4px;
  overflow: hidden;
}
.mode-btn {
  padding: 0.625rem 0.5rem;
  font-size: 0.9375rem;
  background: #2a2a2a;
  color: #c6c6c6;
  border: none;
  border-left: 1px solid #4d4d4d;
  border-top: 1px solid #4d4d4d;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  white-space: nowrap;
}
.mode-btn:nth-child(odd) {
  border-left: none;
}
.mode-btn:nth-child(-n + 2) {
  border-top: none;
}
.mode-btn:hover:not(.active) {
  background: #393939;
  color: #f4f4f4;
}
.mode-btn.active {
  background: #0f62fe;
  color: #ffffff;
  font-weight: 600;
}
.rail-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.segmented {
  display: flex;
  border: 1px solid #4d4d4d;
  border-radius: 4px;
  overflow: hidden;
}
.seg-btn {
  flex: 1;
  padding: 0.625rem 0.5rem;
  font-size: 0.9375rem;
  background: #2a2a2a;
  color: #c6c6c6;
  border: none;
  border-left: 1px solid #4d4d4d;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  white-space: nowrap;
}
.seg-btn:first-child {
  border-left: none;
}
.seg-btn:hover:not(.active) {
  background: #393939;
  color: #f4f4f4;
}
.seg-btn.active {
  background: #0f62fe;
  color: #ffffff;
  font-weight: 600;
}
.rail-action {
  width: 100%;
}
</style>
