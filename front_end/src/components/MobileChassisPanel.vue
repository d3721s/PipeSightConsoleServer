<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api'
import { notify } from '../stores/session'
import {
  leftWheelM,
  rightWheelM,
  leftWheelSpeed,
  rightWheelSpeed,
  statusCode,
  lightD1Pulse,
  lightD3Pulse,
  chassisMode,
  eulerRoll,
  eulerPitch,
  eulerYaw
} from '../stores/odometer'

// Light: fixed period 100; D1/D3 pulse values map to 0-100%.
// Mode: APP = 485 joystick mode (4), 遥控器 = wireless remote (0) (reg 0x50).
const modes: { value: number; label: string }[] = [
  { value: 4, label: 'APP' },
  { value: 0, label: '遥控器' }
]

// Disable the group while a write is awaiting confirmation.
const lightPending = ref(false)
const modePending = ref(false)
const lightD1 = ref('0')
const lightD3 = ref('0')
let lightTimer: number | null = null
let lightSeq = 0

function clampPwm(value: string | number) {
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}

function syncSliderValue(target: typeof lightD1, value: number | null) {
  if (value === null || lightPending.value) return
  target.value = String(clampPwm(value))
}

watch(lightD1Pulse, value => syncSliderValue(lightD1, value), { immediate: true })
watch(lightD3Pulse, value => syncSliderValue(lightD3, value), { immediate: true })

function scheduleLightPwm() {
  const seq = ++lightSeq
  if (lightTimer !== null) window.clearTimeout(lightTimer)
  lightPending.value = true
  lightTimer = window.setTimeout(() => {
    lightTimer = null
    void applyLightPwm(seq)
  }, 180)
}

async function applyLightPwm(seq: number) {
  try {
    const d1 = clampPwm(lightD1.value)
    const d3 = clampPwm(lightD3.value)
    const result = await api.setChassisLightPwm(d1, d3)
    if (seq === lightSeq) {
      lightD1.value = String(clampPwm(result.lightPwm.d1PulseUs))
      lightD3.value = String(clampPwm(result.lightPwm.d3PulseUs))
    }
  } catch {
    if (seq === lightSeq) notify('IMU未确认灯光PWM指令', 'error')
  } finally {
    if (seq === lightSeq) lightPending.value = false
  }
}

async function selectMode(value: number) {
  if (modePending.value || chassisMode.value === value) return
  modePending.value = true
  try {
    await api.setChassisMode(value)
    chassisMode.value = value
    notify('控制模式已设置', 'success')
  } catch (e) {
    notify((e as Error).message || '底盘未确认控制模式指令', 'error')
  } finally {
    modePending.value = false
  }
}

const fmtPulses = (v: number | null) => (v === null ? '--' : `${v}`)
const fmtSpeed = (v: number | null) => (v === null ? '--' : `${v}`)
const fmtText = (v: string | null) => (v === null || v === '' ? '--' : v)
const fmtDeg = (v: number | null) => (v === null ? '--' : `${v.toFixed(1)}°`)
</script>

<template>
  <div class="chassis-group">
    <div class="chassis-section">
      <span class="chassis-label">灯光控制{{ lightPending ? '（设置中…）' : '' }}</span>
      <div class="light-sliders" :class="{ pending: lightPending }">
        <cv-slider
          v-model="lightD1"
          label="D1 灯光"
          min="0"
          max="100"
          min-label="0"
          max-label="100"
          step="1"
          @change="scheduleLightPwm"
        />
        <cv-slider
          v-model="lightD3"
          label="D3 灯光"
          min="0"
          max="100"
          min-label="0"
          max-label="100"
          step="1"
          @change="scheduleLightPwm"
        />
      </div>
    </div>

    <div class="chassis-section">
      <span class="chassis-label">控制模式{{ modePending ? '（设置中…）' : '' }}</span>
      <div class="segmented" :class="{ pending: modePending }">
        <button
          v-for="m in modes"
          :key="m.value"
          type="button"
          class="seg-btn"
          :class="{ active: chassisMode === m.value }"
          :disabled="modePending"
          @click="selectMode(m.value)"
        >{{ m.label }}</button>
      </div>
    </div>

    <div class="chassis-readout">
      <div class="readout-row"><span>左轮里程</span><strong>{{ fmtPulses(leftWheelM) }}</strong></div>
      <div class="readout-row"><span>右轮里程</span><strong>{{ fmtPulses(rightWheelM) }}</strong></div>
      <div class="readout-row"><span>左轮速度</span><strong>{{ fmtSpeed(leftWheelSpeed) }}</strong></div>
      <div class="readout-row"><span>右轮速度</span><strong>{{ fmtSpeed(rightWheelSpeed) }}</strong></div>
      <div class="readout-row"><span>状态码</span><strong>{{ fmtText(statusCode) }}</strong></div>
      <div class="readout-row"><span>横滚角 Roll</span><strong>{{ fmtDeg(eulerRoll) }}</strong></div>
      <div class="readout-row"><span>俯仰角 Pitch</span><strong>{{ fmtDeg(eulerPitch) }}</strong></div>
      <div class="readout-row"><span>航向角 Yaw</span><strong>{{ fmtDeg(eulerYaw) }}</strong></div>
    </div>
  </div>
</template>

<style scoped>
/* Renders inline inside the console control rail (not a separate column). */
.chassis-group {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid #393939;
}
.chassis-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.light-sliders {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.light-sliders.pending {
  opacity: 0.88;
}
.light-sliders :deep(.cv-slider) {
  margin: 0;
}
.light-sliders :deep(.bx--label) {
  color: #ffffff;
  font-size: 0.75rem;
}
.light-sliders :deep(.bx--slider-container) {
  width: 100%;
}
.light-sliders :deep(.bx--slider) {
  flex: 1;
  min-width: 0;
}
.light-sliders :deep(.bx--slider__range-label) {
  color: #ffffff;
  font-size: 0.75rem;
  min-width: 1.5rem;
}
.light-sliders :deep(.bx--slider__track) {
  height: 0.125rem;
  background: #c6c6c6;
}
.light-sliders :deep(.bx--slider__track::before) {
  background: #c6c6c6;
}
.light-sliders :deep(.bx--slider__filled-track) {
  height: 0.125rem;
  background: #ffffff;
}
.light-sliders :deep(.bx--slider__thumb) {
  background: #ffffff;
  box-shadow: 0 0 0 1px #ffffff;
}
.light-sliders :deep(.bx--slider__thumb:hover),
.light-sliders :deep(.bx--slider__thumb:focus),
.light-sliders :deep(.bx--slider__thumb:active) {
  background: #ffffff;
  box-shadow: 0 0 0 2px #ffffff;
}
.light-sliders :deep(.bx--slider-text-input) {
  display: none;
}
.chassis-label {
  color: #ffffff;
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
.segmented.pending {
  opacity: 0.6;
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
.seg-btn:hover:not(.active):not(:disabled) {
  background: #393939;
  color: #f4f4f4;
}
.seg-btn.active {
  background: #0f62fe;
  color: #ffffff;
  font-weight: 600;
}
.seg-btn:disabled {
  cursor: not-allowed;
}
.chassis-readout {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid #393939;
}
.readout-row {
  display: flex;
  justify-content: space-between;
}
.readout-row span {
  color: #8d8d8d;
}
.readout-row strong {
  color: #f4f4f4;
  font-variant-numeric: tabular-nums;
  text-align: right;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
