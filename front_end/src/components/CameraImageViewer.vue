<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

// Renders the RGB or infrared raster stream broadcast by the C++ camera bridge.
// Wire format (binary WebSocket frame, little-endian), see pointcloud_bridge/main.cpp:
//   "IMG1" + u32 width + u32 height + u32 channels + payload(width*height*channels)
//   channels === 3 -> RGB (BGR byte order, SDK CV_8UC3); channels === 1 -> IR gray8.
const props = withDefaults(
  defineProps<{
    wsUrl?: string
    label?: string
  }>(),
  { wsUrl: '', label: '图像' }
)

const HEADER_BYTES = 16

const canvas = ref<HTMLCanvasElement | null>(null)
const connected = ref(false)
const frameInfo = ref('0x0')

const MIN_FRAME_INTERVAL_MS = 66

let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let imageData: ImageData | null = null
let raf = 0
let pendingFrame: ArrayBuffer | null = null
let lastAppliedFrameAt = 0
let disposed = false
let renderQueued = false

function connectWs() {
  if (!props.wsUrl) return
  try {
    ws = new WebSocket(props.wsUrl)
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => {
      connected.value = true
    }
    ws.onmessage = (ev) => {
      if (disposed || !(ev.data instanceof ArrayBuffer)) return
      pendingFrame = ev.data
      requestRender()
    }
    ws.onclose = () => {
      connected.value = false
      if (disposed) return
      scheduleReconnect()
    }
    ws.onerror = () => {
      connected.value = false
    }
  } catch {
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (disposed) return
  if (reconnectTimer !== null) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connectWs()
  }, 2000)
}

function requestRender() {
  if (disposed || renderQueued) return
  renderQueued = true
  raf = requestAnimationFrame(renderQueuedFrame)
}

function renderQueuedFrame() {
  renderQueued = false
  flushPendingFrame()
  if (pendingFrame) requestRender()
}

function flushPendingFrame(force = false) {
  if (!pendingFrame) return
  const now = performance.now()
  if (!force && now - lastAppliedFrameAt < MIN_FRAME_INTERVAL_MS) return
  const buf = pendingFrame
  pendingFrame = null
  renderFrame(buf)
  lastAppliedFrameAt = now
}

function renderFrame(buf: ArrayBuffer) {
  if (buf.byteLength < HEADER_BYTES) return
  const view = new DataView(buf)
  if (
    view.getUint8(0) !== 0x49 || // 'I'
    view.getUint8(1) !== 0x4d || // 'M'
    view.getUint8(2) !== 0x47 || // 'G'
    view.getUint8(3) !== 0x31    // '1'
  ) {
    return
  }

  const width = view.getUint32(4, true)
  const height = view.getUint32(8, true)
  const channels = view.getUint32(12, true)
  if (!width || !height || (channels !== 1 && channels !== 3)) return

  const pixelCount = width * height
  const expected = HEADER_BYTES + pixelCount * channels
  if (buf.byteLength < expected) return

  const el = canvas.value
  const ctx = el?.getContext('2d')
  if (!el || !ctx) return
  if (el.width !== width || el.height !== height) {
    el.width = width
    el.height = height
    imageData = null
  }

  imageData = imageData ?? ctx.createImageData(width, height)
  const rgba = imageData.data
  const src = new Uint8Array(buf, HEADER_BYTES, pixelCount * channels)

  if (channels === 1) {
    // Infrared: 8-bit intensity -> grayscale.
    for (let i = 0, o = 0; i < pixelCount; i++, o += 4) {
      const v = src[i]
      rgba[o] = v
      rgba[o + 1] = v
      rgba[o + 2] = v
      rgba[o + 3] = 255
    }
  } else {
    // RGB: SDK delivers BGR (CV_8UC3); swap to RGBA. If red/blue look swapped on
    // hardware, flip these two indices.
    for (let i = 0, s = 0, o = 0; i < pixelCount; i++, s += 3, o += 4) {
      rgba[o] = src[s + 2]
      rgba[o + 1] = src[s + 1]
      rgba[o + 2] = src[s]
      rgba[o + 3] = 255
    }
  }

  ctx.putImageData(imageData, 0, 0)
  frameInfo.value = `${width}x${height}`
}

function snapshot(): string {
  flushPendingFrame(true)
  const el = canvas.value
  if (!el || el.width === 0 || el.height === 0) return ''
  return el.toDataURL('image/png')
}

defineExpose({ snapshot })

onMounted(() => {
  disposed = false
  connectWs()
})

onBeforeUnmount(() => {
  disposed = true
  cancelAnimationFrame(raf)
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  ws?.close()
  ws = null
  pendingFrame = null
})
</script>

<template>
  <div class="img-root pinch-zoom-surface">
    <canvas ref="canvas" class="img-canvas" />
    <div class="img-status">
      <span :class="['img-dot', connected ? 'on' : 'off']" />
      {{ connected ? `${label}已连接` : (wsUrl ? `等待${label}...` : '') }}
      · {{ frameInfo }}
    </div>
  </div>
</template>

<style scoped>
.img-root {
  position: relative;
  width: 100%;
  height: 100%;
  background: #0b0c0d;
}
.img-canvas {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.img-status {
  position: absolute;
  left: 0.75rem;
  bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: #c6c6c6;
  font-size: 0.8rem;
  background: rgba(22, 22, 22, 0.7);
  padding: 0.2rem 0.6rem;
  border-radius: 2px;
}
.img-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}
.img-dot.on {
  background: #24a148;
}
.img-dot.off {
  background: #da1e28;
}
</style>
