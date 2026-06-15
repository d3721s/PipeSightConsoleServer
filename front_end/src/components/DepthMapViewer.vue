<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    wsUrl?: string
  }>(),
  { wsUrl: '' }
)

const HEADER_BYTES = 16
const FORMAT_U16 = 1
const FORMAT_F32 = 2
const PALETTE_SIZE = 1024

const canvas = ref<HTMLCanvasElement | null>(null)
const connected = ref(false)
const frameInfo = ref('0x0')

let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let imageData: ImageData | null = null

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
      if (!(ev.data instanceof ArrayBuffer)) return
      renderFrame(ev.data)
    }
    ws.onclose = () => {
      connected.value = false
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
  if (reconnectTimer !== null) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    connectWs()
  }, 2000)
}

function renderFrame(buf: ArrayBuffer) {
  // DPT1: magic(4) + width(u32) + height(u32) + format(u32) + raw depth payload.
  if (buf.byteLength < HEADER_BYTES) return
  const view = new DataView(buf)
  if (
    view.getUint8(0) !== 0x44 ||
    view.getUint8(1) !== 0x50 ||
    view.getUint8(2) !== 0x54 ||
    view.getUint8(3) !== 0x31
  ) {
    return
  }

  const width = view.getUint32(4, true)
  const height = view.getUint32(8, true)
  const format = view.getUint32(12, true)
  if (!width || !height) return

  const pixelCount = width * height
  const bytesPerPixel = format === FORMAT_U16 ? 2 : format === FORMAT_F32 ? 4 : 0
  if (!bytesPerPixel) return

  const expected = HEADER_BYTES + pixelCount * bytesPerPixel
  if (buf.byteLength < expected) return

  const values =
    format === FORMAT_U16
      ? new Uint16Array(buf, HEADER_BYTES, pixelCount)
      : new Float32Array(buf, HEADER_BYTES, pixelCount)
  renderDepth(values, width, height, format)
}

function renderDepth(values: Uint16Array | Float32Array, width: number, height: number, format: number) {
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
    const depth = toMeters(values[i], format)
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
    const depth = toMeters(values[i], format)
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

function toMeters(value: number, format: number): number {
  if (format === FORMAT_U16) return value * 0.001
  if (!Number.isFinite(value) || value <= 0) return 0
  return value > 20 ? value * 0.001 : value
}

function snapshot(): string {
  const el = canvas.value
  if (!el || el.width === 0 || el.height === 0) return ''
  return el.toDataURL('image/png')
}

defineExpose({ snapshot })

onMounted(connectWs)

onBeforeUnmount(() => {
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  ws?.close()
  ws = null
})
</script>

<template>
  <div class="depth-root">
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
