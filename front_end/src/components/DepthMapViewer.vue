<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

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

// A depth pixel step larger than this (metres) between neighbours is treated as a
// depth cliff / occlusion edge — triangles spanning it are dropped from area sums.
const DEPTH_CLIFF_M = 0.05

const canvas = ref<HTMLCanvasElement | null>(null)
const connected = ref(false)
const frameInfo = ref('0x0')

const MIN_FRAME_INTERVAL_MS = 66

// Latest decoded depth frame, kept in metres for measurement. `intrinsics` is
// null until the bridge reports it (DPT2); without it we can't compute area.
type DepthFrame = { width: number; height: number; depthM: Float32Array }
type Intrinsics = { fx: number; fy: number; cx: number; cy: number }
let lastDepth: DepthFrame | null = null
let intrinsics: Intrinsics | null = null

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

  // Keep a metres-depth copy of the frame for area measurement.
  const depthM = new Float32Array(pixelCount)
  if (format === FORMAT_U16) {
    const values = new Uint16Array(buf, payloadOffset, pixelCount)
    for (let i = 0; i < pixelCount; i++) depthM[i] = values[i] * 0.001
    renderDepthU16(values, width, height)
  } else {
    const values = new Float32Array(buf, payloadOffset, pixelCount)
    for (let i = 0; i < pixelCount; i++) depthM[i] = normalizeF32Depth(values[i])
    renderDepthF32(values, width, height)
  }
  lastDepth = { width, height, depthM }
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

export type MeasureResult = {
  areaM2: number
  triangles: number
  skipped: number // triangles dropped (invalid depth or depth cliff)
}

// Back-project a depth pixel to a real 3D point (metres). Returns null for
// missing depth. Uses the pinhole model with the camera's depth intrinsics.
function pixelTo3D(u: number, v: number, w: number): [number, number, number] | null {
  if (!intrinsics || !lastDepth) return null
  const z = lastDepth.depthM[v * w + u]
  if (!Number.isFinite(z) || z <= 0) return null
  const x = ((u - intrinsics.cx) * z) / intrinsics.fx
  const y = ((v - intrinsics.cy) * z) / intrinsics.fy
  return [x, y, z]
}

function triArea3D(a: number[], b: number[], c: number[]): number {
  // 0.5 * |(b-a) × (c-a)|
  const abx = b[0] - a[0], aby = b[1] - a[1], abz = b[2] - a[2]
  const acx = c[0] - a[0], acy = c[1] - a[1], acz = c[2] - a[2]
  const cx = aby * acz - abz * acy
  const cy = abz * acx - abx * acz
  const cz = abx * acy - aby * acx
  return 0.5 * Math.sqrt(cx * cx + cy * cy + cz * cz)
}

// Sum the real surface area (m²) of the depth pixels inside a rectangle, by
// triangulating the regular depth grid (2 triangles per pixel quad) and adding
// each triangle's true 3D area. Triangles touching a missing depth, or spanning
// a depth cliff (neighbour step > DEPTH_CLIFF_M), are skipped so occlusion edges
// don't inflate the result. Coordinates are in the depth frame's pixel space.
function measureRect(x0: number, y0: number, x1: number, y1: number): MeasureResult | null {
  const frame = lastDepth
  if (!frame) return null
  if (!intrinsics) return null
  const w = frame.width
  const minX = Math.max(0, Math.min(x0, x1))
  const maxX = Math.min(w - 1, Math.max(x0, x1))
  const minY = Math.max(0, Math.min(y0, y1))
  const maxY = Math.min(frame.height - 1, Math.max(y0, y1))
  if (maxX - minX < 1 || maxY - minY < 1) return null

  const d = frame.depthM
  const notCliff = (z1: number, z2: number) => Math.abs(z1 - z2) <= DEPTH_CLIFF_M
  let area = 0
  let triangles = 0
  let skipped = 0

  // For each pixel quad (TL,TR,BL,BR) emit 2 triangles: TL-TR-BL and TR-BR-BL.
  for (let v = minY; v < maxY; v++) {
    for (let u = minX; u < maxX; u++) {
      const zTL = d[v * w + u]
      const zTR = d[v * w + u + 1]
      const zBL = d[(v + 1) * w + u]
      const zBR = d[(v + 1) * w + u + 1]

      const addTri = (
        ua: number, va: number, za: number,
        ub: number, vb: number, zb: number,
        uc: number, vc: number, zc: number
      ) => {
        if (za <= 0 || zb <= 0 || zc <= 0) { skipped++; return }
        if (!notCliff(za, zb) || !notCliff(zb, zc) || !notCliff(za, zc)) { skipped++; return }
        const A = pixelTo3D(ua, va, w)
        const B = pixelTo3D(ub, vb, w)
        const C = pixelTo3D(uc, vc, w)
        if (!A || !B || !C) { skipped++; return }
        area += triArea3D(A, B, C)
        triangles++
      }

      addTri(u, v, zTL, u + 1, v, zTR, u, v + 1, zBL)
      addTri(u + 1, v, zTR, u + 1, v + 1, zBR, u, v + 1, zBL)
    }
  }

  return { areaM2: area, triangles, skipped }
}

function snapshot(): string {
  flushPendingFrame(true)
  const el = canvas.value
  if (!el || el.width === 0 || el.height === 0) return ''
  return el.toDataURL('image/png')
}

defineExpose({ snapshot, measureRect, hasIntrinsics: () => intrinsics !== null })

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
