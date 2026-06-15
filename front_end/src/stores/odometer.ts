import { ref } from 'vue'
import { api } from '../api'

// Cart odometer distance (metres), polled globally so the OSD overlay distance
// matches what the recorder burns in. Started once from App.vue.

export const distance = ref(0)
export const odometerConnected = ref(false)

// --- Mobile-chassis telemetry (from Modbus via /api/chassis/telemetry) ------
export const leftWheelM = ref<number | null>(null)
export const rightWheelM = ref<number | null>(null)
export const leftWheelSpeed = ref<number | null>(null)
export const rightWheelSpeed = ref<number | null>(null)
export const statusCode = ref<string | null>(null)
export const chassisId = ref<string | null>(null)
export const chassisConnected = ref(false)
export const chassisLight = ref<number | null>(null) // 1 off / 2 low / 3 high
export const chassisMode = ref<number | null>(null)  // 0 remote / 1 speed / 3 pos / 4 joystick
// IMU Euler angles (deg) from ATK-MS901M.
export const imuConnected = ref(false)
export const eulerRoll = ref<number | null>(null)
export const eulerPitch = ref<number | null>(null)
export const eulerYaw = ref<number | null>(null)

let timer: number | null = null
let chassisTimer: number | null = null

export function startOdometerPolling() {
  if (timer === null) {
    timer = window.setInterval(async () => {
      try {
        const data = await api.odometer()
        odometerConnected.value = data.connected
        if (data.mileageM !== null) distance.value = data.mileageM
      } catch {
        // keep last known distance
      }
    }, 250)
  }
  if (chassisTimer === null) {
    chassisTimer = window.setInterval(async () => {
      try {
        const t = await api.chassisTelemetry()
        chassisConnected.value = t.connected
        leftWheelSpeed.value = t.leftSpeed
        rightWheelSpeed.value = t.rightSpeed
        // Mileage is raw encoder pulses for now (no line-count to convert).
        leftWheelM.value = t.leftMileage
        rightWheelM.value = t.rightMileage
        chassisLight.value = t.light
        chassisMode.value = t.mode
        statusCode.value = t.error === null ? null : `0x${t.error.toString(16).padStart(2, '0')}`
        imuConnected.value = t.imuConnected
        eulerRoll.value = t.roll
        eulerPitch.value = t.pitch
        eulerYaw.value = t.yaw
      } catch {
        chassisConnected.value = false
      }
    }, 400)
  }
}

export function stopOdometerPolling() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
  if (chassisTimer !== null) {
    window.clearInterval(chassisTimer)
    chassisTimer = null
  }
}
