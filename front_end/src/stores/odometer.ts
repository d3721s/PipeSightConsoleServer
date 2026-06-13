import { ref } from 'vue'
import { api } from '../api'

// Cart odometer distance (metres), polled globally so the OSD overlay distance
// matches what the recorder burns in. Started once from App.vue.

export const distance = ref(0)
export const odometerConnected = ref(false)
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
