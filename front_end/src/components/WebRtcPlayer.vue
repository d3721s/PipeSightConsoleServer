<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{
  src: string
  digitalZoom: number
}>()

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
let dragStartX = 0
let dragStartY = 0
let dragOriginX = 0
let dragOriginY = 0

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

function onPointerDown(event: PointerEvent) {
  if (props.digitalZoom <= 1) return
  dragging.value = true
  dragStartX = event.clientX
  dragStartY = event.clientY
  dragOriginX = offsetX.value
  dragOriginY = offsetY.value
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return
  offsetX.value = dragOriginX + (event.clientX - dragStartX)
  offsetY.value = dragOriginY + (event.clientY - dragStartY)
  clampOffsets()
}

function onPointerUp(event: PointerEvent) {
  if (!dragging.value) return
  dragging.value = false
  try {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  } catch {
    // pointer may already be released
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

watch(() => props.src, start, { immediate: true })
onBeforeUnmount(() => stop())
</script>

<template>
  <div
    ref="container"
    class="webrtc-player"
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

