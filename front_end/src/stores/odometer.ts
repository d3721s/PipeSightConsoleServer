import { ref } from 'vue'
import { api } from '../api'

// Cart odometer distance (metres), still used for saved media metadata and
// annotation defaults. OSD display uses the left/right chassis wheel mileage.

export const distance = ref(0)
export const odometerConnected = ref(false)

// --- Mobile-chassis telemetry (Modbus chassis + IMU light/attitude) ---------
export const leftWheelM = ref<number | null>(null)
export const rightWheelM = ref<number | null>(null)
export const batteryLevel = ref<number | null>(null)
export const faultCode = ref<string | null>(null)
export const chassisId = ref<string | null>(null)
export const chassisConnected = ref(false)
export const chassisLight = ref<number | null>(null) // 1 off / 2 low / 3 high
export const lightPwmPeriod = ref<number | null>(null)
export const lightD1Pulse = ref<number | null>(null)
export const lightD3Pulse = ref<number | null>(null)
// IMU Euler angles (deg) from ATK-MS901M.
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
        // Chassis mileage is reported in metres after backend pulse conversion.
        leftWheelM.value = t.leftMileage
        rightWheelM.value = t.rightMileage
        batteryLevel.value = t.battery
        faultCode.value = t.faultCode === null ? null : `0x${t.faultCode.toString(16).padStart(2, '0')}`
        chassisLight.value = t.light
        lightPwmPeriod.value = t.lightPwm?.periodUs ?? null
        lightD1Pulse.value = t.lightPwm?.d1PulseUs ?? null
        lightD3Pulse.value = t.lightPwm?.d3PulseUs ?? null
        eulerRoll.value = t.roll
        eulerPitch.value = t.pitch
        eulerYaw.value = t.yaw
      } catch {
        chassisConnected.value = false
        batteryLevel.value = null
        faultCode.value = null
        lightPwmPeriod.value = null
        lightD1Pulse.value = null
        lightD3Pulse.value = null
        eulerRoll.value = null
        eulerPitch.value = null
        eulerYaw.value = null
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
