<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import { notify } from '../stores/session'
import {
  leftWheelM,
  rightWheelM,
  leftWheelSpeed,
  rightWheelSpeed,
  statusCode,
  chassisLight,
  chassisMode,
  imuDiagnostics,
  imuPortOpen,
  imuFresh,
  imuStalled,
  imuLastFrameAgeS,
  imuRxBytes,
  imuValidFrames,
  imuBadFrames,
  imuLastError,
  eulerRoll,
  eulerPitch,
  eulerYaw
} from '../stores/odometer'

// Light: 1 off / 2 low beam / 3 high beam (Modbus reg 0x3D).
// Mode: APP = 485 joystick mode (4), 遥控器 = wireless remote (0) (reg 0x50).
const lights: { value: number; label: string }[] = [
  { value: 1, label: '关闭' },
  { value: 2, label: '近光' },
  { value: 3, label: '远光' }
]
const modes: { value: number; label: string }[] = [
  { value: 4, label: 'APP' },
  { value: 0, label: '遥控器' }
]

// Disable the group while a write is awaiting the chassis confirmation.
const lightPending = ref(false)
const modePending = ref(false)

async function selectLight(value: number) {
  if (lightPending.value || chassisLight.value === value) return
  lightPending.value = true
  try {
    await api.setChassisLight(value)
    chassisLight.value = value // optimistic; telemetry poll will reconcile
    notify('灯光已设置', 'success')
  } catch (e) {
    notify((e as Error).message || '底盘未确认灯光指令', 'error')
  } finally {
    lightPending.value = false
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
const fmtAge = (v: number | null) => (v === null ? '--' : `${v.toFixed(1)}s`)
const imuStatusClass = computed(() => (imuFresh.value ? 'ok' : imuPortOpen.value ? 'warn' : 'off'))
const imuStatusText = computed(() => {
  if (!imuDiagnostics.value && imuFresh.value) return '正常'
  if (!imuDiagnostics.value) return '诊断未启用'
  if (imuFresh.value) return '正常'
  if (imuStalled.value) return '数据停滞'
  if (imuPortOpen.value && (imuRxBytes.value ?? 0) > 0) return '未解析到有效帧'
  if (imuPortOpen.value) return '等待数据帧'
  return '未连接'
})
const imuFrameStats = computed(() => {
  if (!imuDiagnostics.value) return '诊断未启用'
  return `${imuValidFrames.value ?? 0}/${imuBadFrames.value ?? 0}/${imuRxBytes.value ?? 0}`
})
</script>

<template>
  <div class="chassis-group">
    <div class="chassis-section">
      <span class="chassis-label">灯光控制{{ lightPending ? '（设置中…）' : '' }}</span>
      <div class="segmented" :class="{ pending: lightPending }">
        <button
          v-for="l in lights"
          :key="l.value"
          type="button"
          class="seg-btn"
          :class="{ active: chassisLight === l.value }"
          :disabled="lightPending"
          @click="selectLight(l.value)"
        >{{ l.label }}</button>
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
      <div class="readout-row"><span>IMU状态</span><strong class="imu-status" :class="imuStatusClass">{{ imuStatusText }}</strong></div>
      <div class="readout-row"><span>IMU帧龄</span><strong>{{ fmtAge(imuLastFrameAgeS) }}</strong></div>
      <div class="readout-row"><span>有效帧/错帧/字节</span><strong>{{ imuFrameStats }}</strong></div>
      <div v-if="imuDiagnostics && imuLastError" class="readout-row readout-row-error"><span>IMU错误</span><strong>{{ imuLastError }}</strong></div>
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
.chassis-label {
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
.imu-status.ok {
  color: #42be65;
}
.imu-status.warn {
  color: #f1c21b;
}
.imu-status.off {
  color: #fa4d56;
}
.readout-row-error {
  align-items: flex-start;
  gap: 1rem;
}
.readout-row-error strong {
  max-width: 60%;
}
</style>
