<script setup lang="ts">
import { ref } from 'vue'
import { leftWheelM, rightWheelM, leftWheelSpeed, rightWheelSpeed, statusCode, chassisId } from '../stores/odometer'

// Mobile-chassis controls. The backend has no light / control-mode endpoints
// yet, so these toggles only hold UI state for now (mutually exclusive). When
// the backend gains commands, emit from here / call the API.
type Light = 'off' | 'low' | 'high'
type Mode = 'app' | 'remote'

const light = ref<Light>('off')
const mode = ref<Mode>('app')

const lights: { id: Light; label: string }[] = [
  { id: 'off', label: '关闭' },
  { id: 'low', label: '近光' },
  { id: 'high', label: '远光' }
]
const modes: { id: Mode; label: string }[] = [
  { id: 'app', label: 'APP' },
  { id: 'remote', label: '遥控器' }
]

const fmt = (v: number | null) => (v === null ? '--' : `${v.toFixed(2)} m`)
const fmtSpeed = (v: number | null) => (v === null ? '--' : `${v.toFixed(2)} m/s`)
const fmtText = (v: string | null) => (v === null || v === '' ? '--' : v)
</script>

<template>
  <div class="chassis-group">
    <div class="chassis-section">
      <span class="chassis-label">灯光控制</span>
      <div class="segmented">
        <button
          v-for="l in lights"
          :key="l.id"
          type="button"
          class="seg-btn"
          :class="{ active: light === l.id }"
          @click="light = l.id"
        >{{ l.label }}</button>
      </div>
    </div>

    <div class="chassis-section">
      <span class="chassis-label">移动控制模式</span>
      <div class="segmented">
        <button
          v-for="m in modes"
          :key="m.id"
          type="button"
          class="seg-btn"
          :class="{ active: mode === m.id }"
          @click="mode = m.id"
        >{{ m.label }}</button>
      </div>
    </div>

    <div class="chassis-readout">
      <div class="readout-row"><span>左轮里程</span><strong>{{ fmt(leftWheelM) }}</strong></div>
      <div class="readout-row"><span>右轮里程</span><strong>{{ fmt(rightWheelM) }}</strong></div>
      <div class="readout-row"><span>左轮速度</span><strong>{{ fmtSpeed(leftWheelSpeed) }}</strong></div>
      <div class="readout-row"><span>右轮速度</span><strong>{{ fmtSpeed(rightWheelSpeed) }}</strong></div>
      <div class="readout-row"><span>状态码</span><strong>{{ fmtText(statusCode) }}</strong></div>
      <div class="readout-row"><span>ID</span><strong>{{ fmtText(chassisId) }}</strong></div>
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
.chassis-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
/* Mutually-exclusive segmented control, consistent with CameraSwitcher. */
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
}
</style>
