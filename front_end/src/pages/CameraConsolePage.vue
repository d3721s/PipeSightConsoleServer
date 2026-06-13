<script lang="ts">
// Named so <keep-alive include="CameraConsolePage"> keeps the WebRTC preview
// mounted across navigation.
export default { name: 'CameraConsolePage' }
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { CvButton, CvTag } from '@carbon/vue'
import { Camera24, VideoAdd24, StopFilledAlt24, ZoomIn24, ZoomOut24, Report24, ChevronLeft24 } from '@carbon/icons-vue'
import WebRtcPlayer from '../components/WebRtcPlayer.vue'
import OsdOverlay from '../components/OsdOverlay.vue'
import PtzPad from '../components/PtzPad.vue'
import CameraSwitcher from '../components/CameraSwitcher.vue'
import { api } from '../api'
import { cameraControlSocket, type PtzDirection } from '../ws'
import {
  active,
  digitalZoom,
  isPtzChannel,
  loadStream,
  recording,
  selectCamera,
  selectChannel,
  stream
} from '../stores/cameras'
import { distance } from '../stores/odometer'
import { activeReport, currentProject, currentSession, notify, toggleReport } from '../stores/session'

const router = useRouter()

const MIN_ZOOM = 1
const MAX_ZOOM = 4
const ZOOM_STEP = 0.5

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

async function takeSnapshot() {
  try {
    const asset = await api.snapshot({
      projectId: currentProject.value?.id,
      sessionId: currentSession.value?.id,
      device: active.device,
      channel: active.channel,
      distanceM: distance.value,
      projectName: currentProject.value?.name || '',
      projectLocation: currentProject.value?.location || ''
    })
    notify(`拍照已保存 #${(asset as { id?: number }).id ?? ''}`, 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

async function toggleRecording() {
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
      distanceM: distance.value,
      projectName: currentProject.value?.name || '',
      projectLocation: currentProject.value?.location || ''
    })
    window.setTimeout(loadStream, 800)
    notify('录像已开始', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="console-page">
    <div class="video-area">
      <web-rtc-player
        v-if="stream"
        :src="stream.whepUrl"
        v-model:digital-zoom="digitalZoom"
      />
      <div v-else class="video-placeholder">
        请在系统设置中配置相机，并确认 MediaMTX / WebRTC 可用
      </div>

      <osd-overlay
        :distance="distance"
        :project-name="currentProject?.name || ''"
        :location="currentProject?.location || ''"
      />

      <cv-tag v-if="recording.active" kind="red" label="● REC" class="rec-badge" />

      <!-- Bottom-left: zoom cluster -->
      <div class="zoom-cluster">
        <cv-button kind="ghost" size="sm" :icon="ZoomOut24" :disabled="digitalZoom <= MIN_ZOOM" @click="nudgeZoom(-ZOOM_STEP)" />
        <span class="zoom-readout">{{ zoomLabel }}</span>
        <cv-button kind="ghost" size="sm" :icon="ZoomIn24" :disabled="digitalZoom >= MAX_ZOOM" @click="nudgeZoom(ZOOM_STEP)" />
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
        <cv-button kind="ghost" size="sm" :icon="ChevronLeft24" @click="router.push('/')">返回</cv-button>
        <cv-button
          size="sm"
          :kind="activeReport ? 'danger' : 'secondary'"
          :icon="Report24"
          @click="toggleReport"
        >{{ activeReport ? '停止报告' : '开启报告' }}</cv-button>
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
        <cv-button class="rail-action" :icon="Camera24" @click="takeSnapshot">拍照</cv-button>
        <cv-button
          class="rail-action"
          :kind="recording.active ? 'danger' : 'primary'"
          :icon="recording.active ? StopFilledAlt24 : VideoAdd24"
          @click="toggleRecording"
        >{{ recording.active ? '停止录像' : '开始录像' }}</cv-button>
      </div>

      <div class="rail-readout">
        <div><span>距离</span><strong>{{ distance.toFixed(2) }} m</strong></div>
        <div><span>变焦</span><strong>{{ zoomLabel }}</strong></div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.console-page {
  display: grid;
  grid-template-columns: 1fr 18rem;
  height: calc(100vh - 4rem); /* minus Carbon header */
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
  left: 1.25rem;
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
  justify-content: space-between;
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
  justify-content: space-between;
}
.rail-readout {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid #393939;
}
.rail-readout > div {
  display: flex;
  justify-content: space-between;
}
.rail-readout span {
  color: #8d8d8d;
}
.rail-readout strong {
  color: #f4f4f4;
  font-variant-numeric: tabular-nums;
}
</style>
