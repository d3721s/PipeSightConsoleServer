<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{
  src: string
  digitalZoom: number
}>()

const video = ref<HTMLVideoElement | null>(null)
const error = ref('')
const loading = ref(false)
let pc: RTCPeerConnection | null = null
let abortController: AbortController | null = null

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
  <div class="webrtc-player">
    <video
      ref="video"
      autoplay
      muted
      playsinline
      :style="{ transform: `scale(${digitalZoom})` }"
    />
    <div v-if="loading || error || !src" class="player-message">
      <span v-if="error">{{ error }}</span>
      <span v-else-if="!src">无视频源</span>
      <span v-else>视频连接中...</span>
    </div>
  </div>
</template>

