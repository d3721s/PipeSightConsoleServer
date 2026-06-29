<script setup lang="ts">
import { ref, watch } from 'vue'
import { Add24, Reset24, Subtract24 } from '@carbon/icons-vue'
import AttitudePfd from './AttitudePfd.vue'
import { api } from '../api'
import { notify } from '../stores/session'
import {
  CHASSIS_MAX_SPEED_MAX,
  CHASSIS_MAX_SPEED_MIN,
  CHASSIS_MAX_SPEED_STEP,
  chassisMaxSpeed,
  leftWheelM,
  rightWheelM,
  batteryLevel,
  faultCode,
  lightD1Pulse,
  lightD3Pulse,
  eulerRoll,
  eulerPitch,
  eulerYaw,
  setChassisMaxSpeed
} from '../stores/odometer'

// Light: fixed period 100; D1/D3 pulse values map to 0-100%.

// Disable the group while a write is awaiting confirmation.
const lightPending = ref(false)
const odometerPending = ref(false)
const attitudePending = ref(false)
const lightD1 = ref('0')
const lightD3 = ref('0')
let lightTimer: number | null = null
let lightSeq = 0

function clampPwm(value: string | number) {
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}

const pwmDisplay = (value: string) => `${clampPwm(value)}%`

function syncSliderValue(target: typeof lightD1, value: number | null) {
  if (value === null || lightPending.value) return
  target.value = String(clampPwm(value))
}

watch(lightD1Pulse, value => syncSliderValue(lightD1, value), { immediate: true })
watch(lightD3Pulse, value => syncSliderValue(lightD3, value), { immediate: true })

function nudgeLightValue(target: typeof lightD1, delta: number) {
  target.value = String(clampPwm(target.value) + delta)
  scheduleLightPwm()
}

const nudgeD1 = (delta: number) => nudgeLightValue(lightD1, delta)
const nudgeD3 = (delta: number) => nudgeLightValue(lightD3, delta)
const nudgeMaxSpeed = (delta: number) => setChassisMaxSpeed(chassisMaxSpeed.value + delta)

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
    if (seq === lightSeq) notify('灯光设置未生效，请稍后重试', 'error')
  } finally {
    if (seq === lightSeq) lightPending.value = false
  }
}

async function clearOdometer() {
  if (odometerPending.value) return
  odometerPending.value = true
  try {
    await api.clearChassisOdometer()
    leftWheelM.value = 0
    rightWheelM.value = 0
    notify('里程计已清零', 'success')
  } catch {
    notify('里程计清零未成功，请稍后重试', 'error')
  } finally {
    odometerPending.value = false
  }
}

async function calibrateAttitude() {
  if (attitudePending.value) return
  attitudePending.value = true
  try {
    await api.calibrateChassisAttitude()
    notify('已发送姿态清零，请稍候', 'success')
  } catch {
    notify('姿态清零未成功，请检查设备连接后重试', 'error')
  } finally {
    attitudePending.value = false
  }
}

// Carbon confirm dialog shared by the two reset actions; runs the stored action
// on confirm and closes once it settles.
const confirmVisible = ref(false)
const confirmBusy = ref(false)
const confirmInfo = ref<{ title: string; message: string; label: string; run: () => Promise<void> } | null>(null)

function askClearOdometer() {
  confirmInfo.value = {
    title: '里程计清零',
    message: '确定要将左右轮里程计清零吗？清零后将无法恢复。',
    label: '清零',
    run: clearOdometer
  }
  confirmVisible.value = true
}

function askCalibrateAttitude() {
  confirmInfo.value = {
    title: '姿态清零',
    message: '确定要进行姿态清零吗？请先把设备放平、保持静止。',
    label: '清零',
    run: calibrateAttitude
  }
  confirmVisible.value = true
}

async function onConfirm() {
  const info = confirmInfo.value
  if (!info || confirmBusy.value) return
  confirmBusy.value = true
  try {
    await info.run()
    confirmVisible.value = false
  } finally {
    confirmBusy.value = false
  }
}

const fmtMileage = (v: number | null) => (v === null ? '--' : `${v.toFixed(2)} m`)
const fmtBattery = (v: number | null) => (v === null ? '--' : v.toFixed(2))
const fmtText = (v: string | null) => (v === null || v === '' ? '--' : v)
</script>

<template>
  <div class="chassis-group">
    <div class="chassis-attitude">
      <span class="chassis-label">姿态</span>
      <attitude-pfd :roll="eulerRoll" :pitch="eulerPitch" :yaw="eulerYaw" />
      <cv-button
        kind="secondary"
        size="md"
        class="clear-btn"
        :icon="Reset24"
        :disabled="attitudePending"
        @click="askCalibrateAttitude"
      >姿态清零</cv-button>
    </div>

    <div class="chassis-readout">
      <div class="mileage-row">
        <div class="mi"><span class="mi-label">左轮里程</span><span class="mi-value">{{ fmtMileage(leftWheelM) }}</span></div>
        <div class="mi"><span class="mi-label">右轮里程</span><span class="mi-value">{{ fmtMileage(rightWheelM) }}</span></div>
      </div>
      <cv-button
        kind="secondary"
        size="md"
        class="clear-btn"
        :icon="Reset24"
        :disabled="odometerPending"
        @click="askClearOdometer"
      >里程计清零{{ odometerPending ? '（清零中…）' : '' }}</cv-button>
    </div>

    <div class="chassis-controls">
      <div class="chassis-section">
        <span class="chassis-label">灯光{{ lightPending ? '（设置中…）' : '' }}</span>
        <div class="light-sliders" :class="{ pending: lightPending }">
          <div class="pwm-row">
            <span class="pwm-label">灯光1</span>
            <div class="pwm-controls">
              <cv-button kind="ghost" size="sm" class="pwm-btn" :icon="Subtract24" @click="nudgeD1(-10)" />
              <output class="pwm-value">{{ pwmDisplay(lightD1) }}</output>
              <cv-button kind="ghost" size="sm" class="pwm-btn" :icon="Add24" @click="nudgeD1(10)" />
            </div>
          </div>
          <div class="pwm-row">
            <span class="pwm-label">灯光2</span>
            <div class="pwm-controls">
              <cv-button kind="ghost" size="sm" class="pwm-btn" :icon="Subtract24" @click="nudgeD3(-10)" />
              <output class="pwm-value">{{ pwmDisplay(lightD3) }}</output>
              <cv-button kind="ghost" size="sm" class="pwm-btn" :icon="Add24" @click="nudgeD3(10)" />
            </div>
          </div>
        </div>
      </div>

      <div class="chassis-section">
        <span class="chassis-label">最大速度</span>
        <div class="light-sliders">
          <div class="pwm-row">
            <span class="pwm-label">速度</span>
            <div class="pwm-controls">
              <cv-button
                kind="ghost"
                size="sm"
                class="pwm-btn"
                :icon="Subtract24"
                :disabled="chassisMaxSpeed <= CHASSIS_MAX_SPEED_MIN"
                @click="nudgeMaxSpeed(-CHASSIS_MAX_SPEED_STEP)"
              />
              <output class="pwm-value">{{ chassisMaxSpeed }}</output>
              <cv-button
                kind="ghost"
                size="sm"
                class="pwm-btn"
                :icon="Add24"
                :disabled="chassisMaxSpeed >= CHASSIS_MAX_SPEED_MAX"
                @click="nudgeMaxSpeed(CHASSIS_MAX_SPEED_STEP)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="chassis-readout chassis-status">
      <div class="readout-row"><span>电池电量</span><strong>{{ fmtBattery(batteryLevel) }}</strong></div>
      <div class="readout-row"><span>故障码</span><strong>{{ fmtText(faultCode) }}</strong></div>
    </div>

    <cv-modal
      kind="danger"
      :visible="confirmVisible"
      :primary-button-disabled="confirmBusy"
      @update:visible="confirmVisible = $event"
      @primary-click="onConfirm"
      @secondary-click="confirmVisible = false"
    >
      <template #title>{{ confirmInfo?.title }}</template>
      <template #content>
        <p>{{ confirmInfo?.message }}</p>
      </template>
      <template #secondary-button>取消</template>
      <template #primary-button>{{ confirmInfo?.label }}</template>
    </cv-modal>
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
  gap: 0.25rem;
}
/* Divider line between the stacked control sections (灯光 / 最大速度). */
.chassis-controls .chassis-section + .chassis-section {
  padding-top: 0.75rem;
  border-top: 1px solid #393939;
}
.light-sliders {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.light-sliders.pending {
  opacity: 0.88;
}
.pwm-row {
  display: grid;
  grid-template-columns: 2.5rem minmax(0, 1fr);
  align-items: center;
  gap: 0.4rem;
  padding: 0.15rem 0;
}
.pwm-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.pwm-controls {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr) 2rem;
  align-items: center;
  gap: 0.25rem;
  width: 100%;
}
.pwm-btn {
  width: 2rem;
  min-width: 2rem;
  height: 2.25rem;
  padding: 0 !important;
}
.pwm-btn :deep(.bx--btn__icon) {
  right: auto;
}
.pwm-value {
  min-width: 0;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-bottom: 1px solid #8d8d8d;
  background: #f4f4f4;
  color: #161616;
  font-size: 1.0625rem;
  font-weight: 600;
  padding: 0 0.5rem;
}
.chassis-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.clear-btn {
  width: 100%;
  max-width: none;
  min-height: 3rem;
}
.chassis-readout {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid #393939;
}
.chassis-readout .clear-btn {
  margin-top: 0.5rem;
}
/* Left/right wheel mileage read-out: gray caption, white value. */
.mileage-row {
  display: flex;
  gap: 0.75rem;
}
.mi {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}
.mi-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.mi-value {
  color: #f4f4f4;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.chassis-controls {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
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
.chassis-attitude {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
