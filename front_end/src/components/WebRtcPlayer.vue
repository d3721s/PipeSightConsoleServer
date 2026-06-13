<script setup lang="ts">
import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'

const props = defineProps<{
  src: string
  digitalZoom: number
}>()

const emit = defineEmits<{
  (e: 'update:digitalZoom', value: number): void
}>()

const MIN_ZOOM = 1
const MAX_ZOOM = 4

const video = ref<HTMLVideoElement | null>(null)
const container = ref<HTMLDivElement | null>(null)
const error = ref('')
const loading = ref(false)
let pc: RTCPeerConnection | null = null
let abortController: AbortController | null = null

// Pan offset (in CSS pixels) applied before scale. Lets the user drag around a
// digitally-zoomed image to inspect different regions.
const offsetX = ref(0)
const offsetY = ref(0)
const dragging = ref(false)

// Active touch points, keyed by pointerId. 1 pointer => pan, 2 => pinch-zoom.
const points = new Map<number, { x: number; y: number }>()
let dragStartX = 0
let dragStartY = 0
let dragOriginX = 0
let dragOriginY = 0
// Pinch baseline captured when the second finger lands.
let pinchStartDist = 0
let pinchStartZoom = 1

function setZoom(value: number) {
  const clamped = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value))
  emit('update:digitalZoom', clamped)
}

// With transform-origin centered and `translate() scale()`, a zoom of N over a
// box of size W exposes (N-1)*W/2 of slack on each side. Clamp so panning can
// never reveal the black background.
function clampOffsets() {
  const el = container.value
  const zoom = props.digitalZoom
  if (!el || zoom <= 1) {
    offsetX.value = 0
    offsetY.value = 0
    return
  }
  const maxX = ((zoom - 1) * el.clientWidth) / 2
  const maxY = ((zoom - 1) * el.clientHeight) / 2
  offsetX.value = Math.max(-maxX, Math.min(maxX, offsetX.value))
  offsetY.value = Math.max(-maxY, Math.min(maxY, offsetY.value))
}

function twoPointerDistance(): number {
  const [a, b] = [...points.values()]
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function onPointerDown(event: PointerEvent) {
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  points.set(event.pointerId, { x: event.clientX, y: event.clientY })

  if (points.size === 2) {
    // Second finger down: start a pinch, end any single-finger pan.
    dragging.value = false
    pinchStartDist = twoPointerDistance()
    pinchStartZoom = props.digitalZoom
  } else if (points.size === 1 && props.digitalZoom > 1) {
    // One finger on a zoomed image: pan.
    dragging.value = true
    dragStartX = event.clientX
    dragStartY = event.clientY
    dragOriginX = offsetX.value
    dragOriginY = offsetY.value
  }
}

function onPointerMove(event: PointerEvent) {
  const tracked = points.get(event.pointerId)
  if (!tracked) return
  tracked.x = event.clientX
  tracked.y = event.clientY

  if (points.size >= 2) {
    // Pinch: scale zoom by the ratio of current to initial finger spread.
    if (pinchStartDist > 0) {
      const ratio = twoPointerDistance() / pinchStartDist
      setZoom(pinchStartZoom * ratio)
    }
    return
  }

  if (dragging.value) {
    offsetX.value = dragOriginX + (event.clientX - dragStartX)
    offsetY.value = dragOriginY + (event.clientY - dragStartY)
    clampOffsets()
  }
}

function onPointerUp(event: PointerEvent) {
  points.delete(event.pointerId)
  try {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  } catch {
    // pointer may already be released
  }
  if (points.size < 2) {
    pinchStartDist = 0
  }
  if (points.size === 0) {
    dragging.value = false
  } else if (points.size === 1 && props.digitalZoom > 1) {
    // Lifting one finger of a pinch: continue panning with the remaining finger.
    const [remaining] = [...points.values()]
    dragging.value = true
    dragStartX = remaining.x
    dragStartY = remaining.y
    dragOriginX = offsetX.value
    dragOriginY = offsetY.value
  }
}

// Re-clamp (and recenter when back to 1x) whenever the zoom changes.
watch(() => props.digitalZoom, clampOffsets)

function waitIceGatheringComplete(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve) => {
    const timeout = window.setTimeout(resolve, 1200)
    const listener = () => {
      if (peer.iceGatheringState === 'complete') {
        window.clearTimeout(timeout)
        peer.removeEventListener('icegatheringstatechange', listener)
        resolve()
      }
    }
    peer.addEventListener('icegatheringstatechange', listener)
  })
}

async function start() {
  stop()
  if (!props.src) return
  loading.value = true
  error.value = ''
  abortController = new AbortController()

  const peer = new RTCPeerConnection()
  pc = peer
  peer.addTransceiver('video', { direction: 'recvonly' })
  peer.addTransceiver('audio', { direction: 'recvonly' })
  peer.ontrack = (event) => {
    if (video.value && event.streams[0]) {
      video.value.srcObject = event.streams[0]
      video.value.play().catch(() => undefined)
    }
  }

  try {
    const offer = await peer.createOffer()
    await peer.setLocalDescription(offer)
    await waitIceGatheringComplete(peer)
    const localDescription = peer.localDescription
    if (!localDescription?.sdp) throw new Error('无法生成 WebRTC offer')

    const response = await fetch(props.src, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: localDescription.sdp,
      signal: abortController.signal
    })
    if (!response.ok) throw new Error(`WHEP 连接失败：HTTP ${response.status}`)
    const answer = await response.text()
    await peer.setRemoteDescription({ type: 'answer', sdp: answer })
  } catch (err) {
    if ((err as Error).name !== 'AbortError') {
      error.value = (err as Error).message || '视频连接失败'
      stop(false)
    }
  } finally {
    loading.value = false
  }
}

function stop(clearError = true) {
  abortController?.abort()
  abortController = null
  if (pc) {
    pc.getSenders().forEach((sender) => sender.track?.stop())
    pc.getReceivers().forEach((receiver) => receiver.track?.stop())
    pc.close()
    pc = null
  }
  if (video.value) {
    video.value.pause()
    video.value.srcObject = null
  }
  loading.value = false
  if (clearError) error.value = ''
}

// `mounted` tracks whether the very first start has happened. Under
// <keep-alive>, onBeforeUnmount does NOT fire on navigate-away (the component
// is cached, not destroyed), so a WebRTC peer would linger and the stream would
// freeze on return. We tear the connection down on deactivate and rebuild it on
// activate. The `immediate` watch already starts it on first mount, so the
// first onActivated must not double-start.
let started = false

watch(
  () => props.src,
  () => {
    started = true
    start()
  },
  { immediate: true }
)

onActivated(() => {
  // Skip the activation that immediately follows the initial mount.
  if (started) {
    started = false
    return
  }
  start()
})

onDeactivated(() => {
  started = false
  stop()
})

onBeforeUnmount(() => stop())
</script>

<template>
  <div
    ref="container"
    class="webrtc-player interactive"
    :class="{ pannable: digitalZoom > 1, dragging }"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <video
      ref="video"
      autoplay
      muted
      playsinline
      :style="{ transform: `translate(${offsetX}px, ${offsetY}px) scale(${digitalZoom})` }"
    />
    <div v-if="loading || error || !src" class="player-message">
      <span v-if="error">{{ error }}</span>
      <span v-else-if="!src">无视频源</span>
      <span v-else>视频连接中...</span>
    </div>
  </div>
</template>

<style scoped>
.webrtc-player,
.webrtc-player video {
  width: 100%;
  height: 100%;
}

.webrtc-player {
  position: relative;
  overflow: hidden;
}

.webrtc-player video {
  /* contain = show the whole frame letterboxed; never crop/zoom the stream. */
  object-fit: contain;
  transform-origin: center;
  display: block;
}

.webrtc-player.interactive {
  touch-action: none;
}

.webrtc-player.pannable {
  cursor: grab;
}

.webrtc-player.pannable.dragging {
  cursor: grabbing;
}

.player-message {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #9ab0be;
  text-align: center;
  padding: 30px;
  background: #0b0c0d;
}
</style>

