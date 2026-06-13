import { ref } from 'vue'
import { api } from '../api'

// Cart odometer distance (metres), polled globally so the OSD overlay distance
// matches what the recorder burns in. Started once from App.vue.

export const distance = ref(0)
export const odometerConnected = ref(false)

// --- Mobile-chassis telemetry ----------------------------------------------
// The current /api/odometer endpoint only returns { connected, mileageCm,
// mileageM }; it does NOT yet expose per-wheel mileage, a status code, or a
// chassis id. These refs hold those values for the console's 移动底盘 panel and
// stay null (shown as "--") until the backend is extended to provide them.
export const leftWheelM = ref<number | null>(null)
export const rightWheelM = ref<number | null>(null)
export const leftWheelSpeed = ref<number | null>(null)
export const rightWheelSpeed = ref<number | null>(null)
export const statusCode = ref<string | null>(null)
export const chassisId = ref<string | null>(null)

let timer: number | null = null

export function startOdometerPolling() {
  if (timer !== null) return
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

export function stopOdometerPolling() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}
