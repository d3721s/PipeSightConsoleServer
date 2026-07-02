<script lang="ts">
// Named so <keep-alive include="CameraConsolePage"> keeps the WebRTC preview
// mounted across navigation.
export default { name: 'CameraConsolePage' }
</script>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { CvButton, CvTag } from '@carbon/vue'
import { Camera24, VideoAdd24, StopFilledAlt24, ZoomIn24, ZoomOut24, Report24 } from '@carbon/icons-vue'
import WebRtcPlayer from '../components/WebRtcPlayer.vue'
import OsdOverlay from '../components/OsdOverlay.vue'
import PtzPad from '../components/PtzPad.vue'
import Joystick from '../components/Joystick.vue'
import CameraSwitcher from '../components/CameraSwitcher.vue'
import MobileChassisPanel from '../components/MobileChassisPanel.vue'
import { api } from '../api'
import { cameraControlSocket, type PtzDirection } from '../ws'
import {
  active,
  digitalZoom,
  isPtzChannel,
  loadStream,
  recording,
  recordingBusy,
  selectCamera,
  selectChannel,
  stream
} from '../stores/cameras'
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

const props = withDefaults(defineProps<{ active?: boolean }>(), { active: true })
type WebRtcPlayerHandle = {
  snapshot: () => string
}

const MIN_ZOOM = 1
const MAX_ZOOM = 4
const ZOOM_STEP = 0.5
const player = ref<WebRtcPlayerHandle | null>(null)
const videoArea = ref<HTMLDivElement | null>(null)

function nudgeZoom(delta: number) {
  digitalZoom.value = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, +(digitalZoom.value + delta).toFixed(2)))
}

const zoomLabel = computed(() => `${digitalZoom.value.toFixed(1)}x`)

function ptzStep(direction: PtzDirection) {
  cameraControlSocket.step(active.device, active.channel, direction)
}
function ptzStart(direction: PtzDirection) {
  cameraControlSocket.start(active.device, active.channel, direction)
}
function ptzStop() {
  cameraControlSocket.stop(active.device, active.channel)
}

function onChassisMove(v: { x: number; y: number }) {
  sendChassisMove(v.x, v.y)
}

async function takeSnapshot() {
  try {
    const dataUrl = player.value?.snapshot()
    if (!dataUrl) {
      notify('视频画面还没准备好，请稍候再试', 'warning')
      return
    }
    const image = await addOsdToSnapshot(dataUrl)
    const asset = await api.imageSnapshot({
      projectId: currentProject.value?.id,
      sessionId: currentSession.value?.id,
      leftMileage: leftWheelM.value,
      rightMileage: rightWheelM.value,
      image,
      source: 'camera',
      device: active.device,
      channel: active.channel
    })
    notify(`拍照已保存 #${(asset as { id?: number }).id ?? ''}`, 'success')
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

  const scaleX = width / areaRect.width
  const scaleY = height / areaRect.height
  const style = getComputedStyle(osd)
  const fontSizeCss = Number.parseFloat(style.fontSize) || 13
  const lineHeightCss = Number.parseFloat(style.lineHeight) || fontSizeCss * 1.45
  const paddingLeft = Number.parseFloat(style.paddingLeft) || 0
  const paddingTop = Number.parseFloat(style.paddingTop) || 0
  const borderLeft = Number.parseFloat(style.borderLeftWidth) || 3

  return {
    x: Math.round((osdRect.left - areaRect.left) * scaleX),
    y: Math.round((osdRect.top - areaRect.top) * scaleY),
    borderWidth: Math.max(1, Math.round(borderLeft * scaleX)),
    fontSize: Math.max(12, Math.round(fontSizeCss * scaleY)),
    lineHeight: Math.max(14, Math.round(lineHeightCss * scaleY)),
    paddingX: Math.max(4, Math.round(paddingLeft * scaleX)),
    paddingY: Math.max(4, Math.round(paddingTop * scaleY))
  }
}

async function toggleRecording() {
  if (recordingBusy.value) return
  recordingBusy.value = true
  try {
    if (recording.value.active) {
      recording.value = await api.stopRecording()
      await loadStream()
      notify('录像已停止', 'info')
      return
    }
    recording.value = await api.startRecording({
      projectId: currentProject.value?.id,
      sessionId: currentSession.value?.id,
      device: active.device,
      channel: active.channel,
      leftMileage: leftWheelM.value,
      rightMileage: rightWheelM.value,
      projectName: currentProject.value?.name || '',
      projectLocation: currentProject.value?.location || ''
    })
    window.setTimeout(loadStream, 800)
    notify('录像已开始', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    recordingBusy.value = false
  }
}
</script>

<template>
  <div class="console-page">
    <div ref="videoArea" class="video-area">
      <web-rtc-player
        v-if="stream"
        ref="player"
        :src="stream.whepUrl"
        :active="props.active"
        v-model:digital-zoom="digitalZoom"
      />
      <div v-else class="video-placeholder">
        请在系统设置中配置相机
      </div>

      <osd-overlay
        :left-mileage="leftWheelM"
        :right-mileage="rightWheelM"
        :project-name="currentProject?.name || ''"
        :location="currentProject?.location || ''"
      />

      <cv-tag v-if="recording.active" kind="red" label="● REC" class="rec-badge" />

      <!-- Bottom-left: chassis joystick -->
      <div class="chassis-cluster">
        <joystick :range="chassisMaxSpeed" :disabled="!chassisControlEnabled" @move="onChassisMove" />
      </div>

      <!-- Bottom-center: zoom cluster -->
      <div class="zoom-cluster">
        <cv-button class="bx--btn--icon-only zoom-btn" kind="ghost" size="sm" :icon="ZoomOut24" :disabled="digitalZoom <= MIN_ZOOM" @click="nudgeZoom(-ZOOM_STEP)" />
        <span class="zoom-readout">{{ zoomLabel }}</span>
        <cv-button class="bx--btn--icon-only zoom-btn" kind="ghost" size="sm" :icon="ZoomIn24" :disabled="digitalZoom >= MAX_ZOOM" @click="nudgeZoom(ZOOM_STEP)" />
      </div>

      <!-- Bottom-right: PTZ pad -->
      <div class="ptz-cluster">
        <span class="ptz-caption">云台控制{{ isPtzChannel ? '' : '（仅云台通道）' }}</span>
        <ptz-pad
          :disabled="!isPtzChannel"
          @step="ptzStep"
          @start="ptzStart"
          @stop="ptzStop"
        />
      </div>
    </div>

    <aside class="control-rail">
      <div class="rail-top">
        <cv-button
          class="rail-action"
          :kind="activeReport ? 'danger' : 'primary'"
          :icon="Report24"
          :disabled="reportToggling"
          @click="toggleReport"
        >{{ reportToggling ? '处理中' : activeReport ? '停止报告' : '开启报告' }}</cv-button>
      </div>

      <div class="rail-section">
        <span class="rail-label">相机 </span>
        <camera-switcher
          :device="active.device"
          :channel="active.channel"
          @select-device="(d) => selectCamera(d)"
          @select-channel="(c) => selectChannel(c)"
        />
      </div>

      <div class="rail-section">
        <span class="rail-label">采集</span>
        <div class="capture-row">
          <cv-button class="capture-btn" :icon="Camera24" @click="takeSnapshot">拍照</cv-button>
          <cv-button
            class="capture-btn"
            :kind="recording.active ? 'danger' : 'primary'"
            :icon="recording.active ? StopFilledAlt24 : VideoAdd24"
            :disabled="recordingBusy"
            @click="toggleRecording"
          >{{ recording.active ? '停止' : '录制' }}</cv-button>
        </div>
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
  grid-template-columns: 1fr 15rem;
  height: 100%; /* fill .app-content (pinned to viewport-minus-header) */
  background: #000;
}
.video-area {
  position: relative;
  overflow: hidden;
  background: #000;
}
.video-area :deep(.webrtc-player) {
  width: 100%;
  height: 100%;
}
.video-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #8d8d8d;
  padding: 2rem;
  text-align: center;
}
.rec-badge {
  position: absolute;
  top: 1rem;
  right: 1rem;
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
.zoom-readout {
  min-width: 2.5rem;
  text-align: center;
  color: #f4f4f4;
  font-variant-numeric: tabular-nums;
}
/* Icon-only zoom buttons: enlarge the glyph to match the scaled UI (the global
   icon-enlarge rule intentionally skips icon-only buttons). */
.zoom-btn :deep(.bx--btn__icon) {
  width: 1.5rem;
  height: 1.5rem;
}
/* Both zoom buttons sit on a dark pill; force their glyphs solid white in every
   state (incl. disabled at a zoom limit) so the two buttons always match.
   Carbon ghost defaults to a dark glyph and a different grey when disabled,
   which made the two buttons look inconsistent. */
.zoom-btn :deep(svg),
.zoom-btn:hover :deep(svg),
.zoom-btn:focus :deep(svg),
.zoom-btn:disabled :deep(svg),
.zoom-btn.bx--btn--disabled :deep(svg) {
  fill: #ffffff;
}
.ptz-cluster {
  position: absolute;
  right: 1.25rem;
  bottom: 1.25rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}
.ptz-caption {
  color: #c6c6c6;
  font-size: 0.75rem;
  background: rgba(22, 22, 22, 0.7);
  padding: 0.125rem 0.5rem;
  border-radius: 2px;
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
  /* Match the capture button's icon-reserve so a long CJK label (处理中/停止报告)
     never slides under Carbon's absolutely-positioned right icon. */
  padding-left: 0.75rem !important;
  padding-right: 2rem !important;
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
.capture-row {
  display: flex;
  gap: 0.5rem;
}
/* .capture-btn IS the Carbon <button> (cv-button + bx--btn on one element).
   Two buttons share the 15rem rail, so trim Carbon's wide icon reserve and let
   each flex to half width, keeping "拍照"/"录制" on one line. */
.capture-btn {
  flex: 1 1 0;
  min-width: 0;
  /* Override Carbon's wide icon reserve (.bx--btn:has(icon) sets 3rem) so two
     buttons fit side by side in the 15rem rail without the label clipping. */
  padding-left: 0.75rem !important;
  padding-right: 2rem !important;
}
</style>
