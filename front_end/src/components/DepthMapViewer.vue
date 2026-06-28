<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { encodeDepthRaw, type DepthIntrinsics } from '../utils/depthArea'

const props = withDefaults(
  defineProps<{
    wsUrl?: string
  }>(),
  { wsUrl: '' }
)

const HEADER_BYTES = 16
const HEADER_BYTES_V2 = 32 // DPT2 adds fx,fy,cx,cy (4 float32) after `format`
const FORMAT_U16 = 1
const FORMAT_F32 = 2
const PALETTE_SIZE = 1024

const canvas = ref<HTMLCanvasElement | null>(null)
const connected = ref(false)
const frameInfo = ref('0x0')

const MIN_FRAME_INTERVAL_MS = 66

// Latest raw depth frame (u16 millimetres, as received) + intrinsics, kept so a
// snapshot can export the raw depth for later area measurement on the annotate
// page. `intrinsics` is null until the bridge reports it (DPT2).
type RawDepthFrame = { width: number; height: number; depthMm: Uint16Array }
let lastDepth: RawDepthFrame | null = null
let intrinsics: DepthIntrinsics | null = null

let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let imageData: ImageData | null = null
let raf = 0
let pendingFrame: ArrayBuffer | null = null
let lastAppliedFrameAt = 0
let disposed = false
let renderQueued = false

const palette = buildPalette()

function buildPalette(): Uint8ClampedArray {
  const stops = [
    [0, 0, 0],
    [0, 56, 180],
    [0, 210, 255],
    [0, 210, 80],
    [250, 220, 0],
    [255, 70, 0],
    [255, 255, 255]
  ]
  const out = new Uint8ClampedArray(PALETTE_SIZE * 3)
  for (let i = 0; i < PALETTE_SIZE; i++) {
    const t = i / (PALETTE_SIZE - 1)
    const scaled = t * (stops.length - 1)
    const idx = Math.min(stops.length - 2, Math.floor(scaled))
    const local = scaled - idx
    const a = stops[idx]
    const b = stops[idx + 1]
    out[i * 3] = a[0] + (b[0] - a[0]) * local
    out[i * 3 + 1] = a[1] + (b[1] - a[1]) * local
    out[i * 3 + 2] = a[2] + (b[2] - a[2]) * local
  }
  return out
}

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
  // magic(4) + width(u32) + height(u32) + format(u32) + [DPT2: fx,fy,cx,cy f32] + payload.
  if (buf.byteLength < HEADER_BYTES) return
  const view = new DataView(buf)
  // 'D' 'P' 'T', then '1' (legacy) or '2' (with intrinsics).
  if (view.getUint8(0) !== 0x44 || view.getUint8(1) !== 0x50 || view.getUint8(2) !== 0x54) return
  const ver = view.getUint8(3)
  if (ver !== 0x31 && ver !== 0x32) return
  const isV2 = ver === 0x32

  const width = view.getUint32(4, true)
  const height = view.getUint32(8, true)
  const format = view.getUint32(12, true)
  if (!width || !height) return

  let payloadOffset = HEADER_BYTES
  if (isV2) {
    if (buf.byteLength < HEADER_BYTES_V2) return
    const fx = view.getFloat32(16, true)
    const fy = view.getFloat32(20, true)
    const cx = view.getFloat32(24, true)
    const cy = view.getFloat32(28, true)
    // Bridge sends zeros until the camera reports intrinsics; keep last good set.
    intrinsics = fx !== 0 && fy !== 0 ? { fx, fy, cx, cy } : intrinsics
    payloadOffset = HEADER_BYTES_V2
  }

  const pixelCount = width * height
  const bytesPerPixel = format === FORMAT_U16 ? 2 : format === FORMAT_F32 ? 4 : 0
  if (!bytesPerPixel) return

  const expected = payloadOffset + pixelCount * bytesPerPixel
  if (buf.byteLength < expected) return

  // Keep a raw u16 (mm) copy of the frame so a snapshot can export it for
  // area measurement on the annotate page.
  if (format === FORMAT_U16) {
    const values = new Uint16Array(buf, payloadOffset, pixelCount)
    lastDepth = { width, height, depthMm: values.slice() }
    renderDepthU16(values, width, height)
  } else {
    const values = new Float32Array(buf, payloadOffset, pixelCount)
    const mm = new Uint16Array(pixelCount)
    for (let i = 0; i < pixelCount; i++) {
      const m = normalizeF32Depth(values[i])
      mm[i] = m > 0 ? Math.min(65535, Math.round(m * 1000)) : 0
    }
    lastDepth = { width, height, depthMm: mm }
    renderDepthF32(values, width, height)
  }
}

function renderDepthU16(values: Uint16Array, width: number, height: number) {
  const el = canvas.value
  const ctx = el?.getContext('2d')
  if (!el || !ctx) return

  if (el.width !== width || el.height !== height) {
    el.width = width
    el.height = height
    imageData = null
  }

  let minDepth = Infinity
  let maxDepth = -Infinity
  let valid = 0
  for (let i = 0; i < values.length; i++) {
    const raw = values[i]
    if (!raw) continue
    const depth = raw * 0.001
    valid++
    if (depth < minDepth) minDepth = depth
    if (depth > maxDepth) maxDepth = depth
  }

  if (!valid) {
    ctx.clearRect(0, 0, width, height)
    frameInfo.value = `${width}x${height} · 无有效深度`
    return
  }

  const span = maxDepth > minDepth ? maxDepth - minDepth : 0.001
  imageData = imageData ?? ctx.createImageData(width, height)
  const rgba = imageData.data
  for (let i = 0, o = 0; i < values.length; i++, o += 4) {
    const raw = values[i]
    if (!raw) {
      rgba[o] = 0
      rgba[o + 1] = 0
      rgba[o + 2] = 0
      rgba[o + 3] = 255
      continue
    }

    const t = Math.max(0, Math.min(1, (raw * 0.001 - minDepth) / span))
    const p = Math.round(t * (PALETTE_SIZE - 1)) * 3
    rgba[o] = palette[p]
    rgba[o + 1] = palette[p + 1]
    rgba[o + 2] = palette[p + 2]
    rgba[o + 3] = 255
  }

  ctx.putImageData(imageData, 0, 0)
  frameInfo.value = `${width}x${height} · ${minDepth.toFixed(2)}-${maxDepth.toFixed(2)} m`
}

function renderDepthF32(values: Float32Array, width: number, height: number) {
  const el = canvas.value
  const ctx = el?.getContext('2d')
  if (!el || !ctx) return

  if (el.width !== width || el.height !== height) {
    el.width = width
    el.height = height
    imageData = null
  }

  let minDepth = Infinity
  let maxDepth = -Infinity
  let valid = 0
  for (let i = 0; i < values.length; i++) {
    const depth = normalizeF32Depth(values[i])
    if (!Number.isFinite(depth) || depth <= 0) continue
    valid++
    if (depth < minDepth) minDepth = depth
    if (depth > maxDepth) maxDepth = depth
  }

  if (!valid) {
    ctx.clearRect(0, 0, width, height)
    frameInfo.value = `${width}x${height} · 无有效深度`
    return
  }

  const span = maxDepth > minDepth ? maxDepth - minDepth : 0.001
  imageData = imageData ?? ctx.createImageData(width, height)
  const rgba = imageData.data

  for (let i = 0, o = 0; i < values.length; i++, o += 4) {
    const depth = normalizeF32Depth(values[i])
    if (!Number.isFinite(depth) || depth <= 0) {
      rgba[o] = 0
      rgba[o + 1] = 0
      rgba[o + 2] = 0
      rgba[o + 3] = 255
      continue
    }

    const t = Math.max(0, Math.min(1, (depth - minDepth) / span))
    const p = Math.round(t * (PALETTE_SIZE - 1)) * 3
    rgba[o] = palette[p]
    rgba[o + 1] = palette[p + 1]
    rgba[o + 2] = palette[p + 2]
    rgba[o + 3] = 255
  }

  ctx.putImageData(imageData, 0, 0)
  frameInfo.value = `${width}x${height} · ${minDepth.toFixed(2)}-${maxDepth.toFixed(2)} m`
}

function normalizeF32Depth(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0
  return value > 20 ? value * 0.001 : value
}

// Export the latest depth frame (raw u16 mm + intrinsics) as a compact blob, so
// a snapshot can be measured later on the annotate page. Null if no frame yet or
// the camera intrinsics aren't available.
function exportDepthRaw(): ArrayBuffer | null {
  if (!lastDepth || !intrinsics) return null
  return encodeDepthRaw(lastDepth.width, lastDepth.height, lastDepth.depthMm, intrinsics)
}

function snapshot(): string {
  flushPendingFrame(true)
  const el = canvas.value
  if (!el || el.width === 0 || el.height === 0) return ''
  return el.toDataURL('image/png')
}

defineExpose({ snapshot, exportDepthRaw, hasIntrinsics: () => intrinsics !== null })

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
  <div class="depth-root pinch-zoom-surface">
    <canvas ref="canvas" class="depth-canvas" />
    <div class="depth-status">
      <span :class="['depth-dot', connected ? 'on' : 'off']" />
      {{ connected ? '深度图已连接' : (wsUrl ? '等待深度图...' : '') }}
      · {{ frameInfo }}
    </div>
  </div>
</template>

<style scoped>
.depth-root {
  position: relative;
  width: 100%;
  height: 100%;
  background: #0b0c0d;
}
.depth-canvas {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.depth-status {
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
.depth-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}
.depth-dot.on {
  background: #24a148;
}
.depth-dot.off {
  background: #da1e28;
}
</style>
