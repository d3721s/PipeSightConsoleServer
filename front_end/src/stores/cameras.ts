import { computed, reactive, ref } from 'vue'
import { api } from '../api'
import type { ActiveCamera, CameraCode, CameraDevice, RecordingStatus, StreamInfo } from '../types'

// Global camera / stream / recording state. Lives at module scope so the console
// preview and its WebRTC connection survive route changes.

export const cameras = ref<CameraDevice[]>([])
export const active = reactive<ActiveCamera>({ device: 'front', channel: 1 })
export const stream = ref<StreamInfo | null>(null)
export const recording = ref<RecordingStatus>({ active: false })
// True while a start/stop recording request is in flight, so the background
// status poll skips that window and doesn't fight the in-progress action.
export const recordingBusy = ref(false)
export const digitalZoom = ref(1)

export const activeCamera = computed(() => cameras.value.find((c) => c.code === active.device))
export const isPtzChannel = computed(() => active.channel === 1)

let loaded = false

export async function loadCameras() {
  cameras.value = await api.listCameras()
  const state = await api.getActiveCamera()
  active.device = state.device
  active.channel = state.channel
  recording.value = await api.recordingStatus()
}

// Load camera state + stream once on first app mount.
export async function ensureLoaded() {
  if (loaded) return
  loaded = true
  await loadCameras()
  await loadStream()
}

export async function loadStream() {
  try {
    stream.value = await api.getActiveStream()
  } catch {
    stream.value = null
  }
}

export async function selectCamera(device: CameraCode, channel = active.channel) {
  active.device = device
  active.channel = channel
  await api.setActiveCamera({ device, channel })
  digitalZoom.value = 1
  await loadStream()
}

export async function selectChannel(channel: number) {
  active.channel = channel
  await api.setActiveCamera({ device: active.device, channel })
  digitalZoom.value = 1
  await loadStream()
}
