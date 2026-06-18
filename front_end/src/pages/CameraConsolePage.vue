<script lang="ts">
// Named so <keep-alive include="CameraConsolePage"> keeps the WebRTC preview
// mounted across navigation.
export default { name: 'CameraConsolePage' }
</script>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvButton, CvTag } from '@carbon/vue'
import { Camera24, VideoAdd24, StopFilledAlt24, ZoomIn24, ZoomOut24, Report24, ChevronLeft24 } from '@carbon/icons-vue'
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
  selectCamera,
  selectChannel,
  stream
} from '../stores/cameras'
import { leftWheelM, rightWheelM } from '../stores/odometer'
import { activeReport, currentProject, currentSession, notify, reportToggling, toggleReport } from '../stores/session'

const router = useRouter()
const props = withDefaults(defineProps<{ active?: boolean }>(), { active: true })
const chassisControlEnabled = ref(false)

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

function onChassisMove(v: { x: number; y: number }) {
  if (!chassisControlEnabled.value) return
  cameraControlSocket.chassisMove(v.x, v.y)
}

async function takeSnapshot() {
  try {
    const asset = await api.snapshot({
      projectId: currentProject.value?.id,
      sessionId: currentSession.value?.id,
      device: active.device,
      channel: active.channel,
      leftMileage: leftWheelM.value,
      rightMileage: rightWheelM.value,
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
      leftMileage: leftWheelM.value,
      rightMileage: rightWheelM.value,
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
        :active="props.active"
        v-model:digital-zoom="digitalZoom"
      />
      <div v-else class="video-placeholder">
        请在系统设置中配置相机，并确认 MediaMTX / WebRTC 可用
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
        <joystick :disabled="!chassisControlEnabled" @move="onChassisMove" />
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
            @click="toggleRecording"
          >{{ recording.active ? '停止录像' : '开始录像' }}</cv-button>
        </div>
      </div>

      <div class="rail-section">
        <span class="rail-label">底盘</span>
        <div class="chassis-enable-toggle bx--form-item">
          <input
            id="chassis-control-enabled"
            v-model="chassisControlEnabled"
            class="bx--toggle-input"
            type="checkbox"
            value="enabled"
          />
          <label class="bx--toggle-input__label" for="chassis-control-enabled">
            摇杆控制
            <span class="bx--toggle__switch">
              <svg class="bx--toggle__check" width="6px" height="5px" viewBox="0 0 6 5">
                <path d="M2.2 2.7L5 0 6 1 2.2 5 0 2.7 1 1.5z" />
              </svg>
              <span class="bx--toggle__text--off" aria-hidden="true">关闭</span>
              <span class="bx--toggle__text--on" aria-hidden="true">开启</span>
            </span>
          </label>
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
.chassis-enable-toggle :deep(.bx--toggle-input__label) {
  color: #f4f4f4;
}
.chassis-enable-toggle :deep(.bx--toggle__text--off),
.chassis-enable-toggle :deep(.bx--toggle__text--on) {
  color: #161616;
}
.capture-row {
  display: flex;
  gap: 0.5rem;
}
/* .capture-btn IS the Carbon <button> (cv-button + bx--btn on one element).
   Two buttons share the 18rem rail, so trim Carbon's wide icon reserve and let
   each flex to half width, keeping "拍照"/"开始录像" on one line. */
.capture-btn {
  flex: 1 1 0;
  min-width: 0;
  /* Override Carbon's wide icon reserve (.bx--btn:has(icon) sets 3rem) so two
     buttons fit side by side in the 18rem rail without the label clipping. */
  padding-left: 0.75rem !important;
  padding-right: 2rem !important;
}
</style>
