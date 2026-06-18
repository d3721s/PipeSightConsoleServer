<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const props = withDefaults(
  defineProps<{
    // WebSocket URL of the C++ point-cloud bridge. Empty => demo data only.
    wsUrl?: string
    pointSize?: number
  }>(),
  { wsUrl: '', pointSize: 0.012 }
)
const emit = defineEmits<{
  (event: 'zoom-change', value: number): void
}>()

const container = ref<HTMLDivElement | null>(null)
const connected = ref(false)
const pointCount = ref(0)

const MIN_FRAME_INTERVAL_MS = 66
const COLOR_STEPS = 512
const DEFAULT_VIEW_ZOOM = 1.2
const MIN_VIEW_ZOOM = 0.2
const MAX_VIEW_ZOOM = 8

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let points: THREE.Points | null = null
let geometry: THREE.BufferGeometry | null = null
let raf = 0
let ws: WebSocket | null = null
let reconnectTimer: number | null = null
let resizeObs: ResizeObserver | null = null
let framedFirstCloud = false
let pendingFrame: ArrayBuffer | null = null
let lastAppliedFrameAt = 0
let positionAttribute: THREE.BufferAttribute | null = null
let colorAttribute: THREE.BufferAttribute | null = null
let colorArray: Float32Array | null = null
let disposed = false
let renderQueued = false
let baseZoomDistance = 0
let lastEmittedZoom = 0
const onControlsChange = () => {
  requestRender()
  emitZoomChange()
}

const pointColorPalette = buildPointColorPalette()

function buildPointColorPalette(): Float32Array {
  const out = new Float32Array(COLOR_STEPS * 3)
  const color = new THREE.Color()
  for (let i = 0; i < COLOR_STEPS; i++) {
    const t = i / (COLOR_STEPS - 1)
    color.setHSL(0.7 - 0.7 * t, 0.9, 0.5)
    out[i * 3] = color.r
    out[i * 3 + 1] = color.g
    out[i * 3 + 2] = color.b
  }
  return out
}

function initThree() {
  const el = container.value!
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0b0c0d)

  camera = new THREE.PerspectiveCamera(60, el.clientWidth / el.clientHeight, 0.01, 1000)
  camera.position.set(0, 0, 2)

  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setSize(el.clientWidth, el.clientHeight)
  renderer.domElement.style.touchAction = 'none'
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.addEventListener('change', onControlsChange)

  // A subtle grid + axes for spatial reference.
  const grid = new THREE.GridHelper(4, 16, 0x393939, 0x262626)
  grid.rotation.x = Math.PI / 2 // grid in XY so it sits "behind" the cloud
  scene.add(grid)

  geometry = new THREE.BufferGeometry()
  const material = new THREE.PointsMaterial({
    size: props.pointSize,
    vertexColors: true,
    sizeAttenuation: true
  })
  points = new THREE.Points(geometry, material)
  scene.add(points)

  requestRender()
}

function requestRender() {
  if (disposed || renderQueued) return
  renderQueued = true
  raf = requestAnimationFrame(renderFrame)
}

function renderFrame() {
  renderQueued = false
  const processed = flushPendingFrame()
  const controlsChanged = controls?.update() ?? false
  if (renderer && scene && camera) renderer.render(scene, camera)
  if (pendingFrame || processed || controlsChanged) {
    requestRender()
  }
}

function flushPendingFrame(force = false): boolean {
  if (!pendingFrame) return false
  const now = performance.now()
  if (!force && now - lastAppliedFrameAt < MIN_FRAME_INTERVAL_MS) return false
  const buf = pendingFrame
  pendingFrame = null
  processFrame(buf)
  lastAppliedFrameAt = now
  return true
}

function processFrame(buf: ArrayBuffer) {
  if (buf.byteLength < 8) return
  const view = new DataView(buf)
  // magic "PCD1"
  if (view.getUint8(0) !== 0x50 || view.getUint8(1) !== 0x43) return
  const count = view.getUint32(4, true)
  const expected = 8 + count * 3 * 4
  if (buf.byteLength < expected) return
  const xyz = new Float32Array(buf, 8, count * 3)
  setPoints(xyz)
}

// Replace the point cloud. `xyz` is a flat Float32Array [x,y,z, x,y,z, ...].
function setPoints(xyz: Float32Array) {
  if (!geometry) return
  const count = Math.floor(xyz.length / 3)
  pointCount.value = count

  if (positionAttribute && positionAttribute.array instanceof Float32Array && positionAttribute.array.length === xyz.length) {
    positionAttribute.array.set(xyz)
    positionAttribute.needsUpdate = true
  } else {
    positionAttribute = new THREE.BufferAttribute(xyz, 3)
    positionAttribute.setUsage(THREE.DynamicDrawUsage)
    geometry.setAttribute('position', positionAttribute)
  }

  // Color points by depth (z) for readability.
  if (!colorArray || colorArray.length !== count * 3) {
    colorArray = new Float32Array(count * 3)
    colorAttribute = new THREE.BufferAttribute(colorArray, 3)
    colorAttribute.setUsage(THREE.DynamicDrawUsage)
    geometry.setAttribute('color', colorAttribute)
  }
  const colors = colorArray
  let zmin = Infinity
  let zmax = -Infinity
  for (let i = 0; i < count; i++) {
    const z = xyz[i * 3 + 2]
    if (z < zmin) zmin = z
    if (z > zmax) zmax = z
  }
  const span = zmax - zmin || 1
  for (let i = 0; i < count; i++) {
    const t = (xyz[i * 3 + 2] - zmin) / span
    const p = Math.max(0, Math.min(COLOR_STEPS - 1, Math.floor(t * (COLOR_STEPS - 1)))) * 3
    colors[i * 3] = pointColorPalette[p]
    colors[i * 3 + 1] = pointColorPalette[p + 1]
    colors[i * 3 + 2] = pointColorPalette[p + 2]
  }

  if (colorAttribute) {
    colorAttribute.needsUpdate = true
  }
  if (!framedFirstCloud) {
    frameCloud()
    framedFirstCloud = true
  }
}

function frameCloud() {
  if (!geometry || !camera || !controls) return
  geometry.computeBoundingBox()
  const box = geometry.boundingBox
  if (!box || box.isEmpty()) return
  const center = new THREE.Vector3()
  const size = new THREE.Vector3()
  box.getCenter(center)
  box.getSize(size)
  const radius = Math.max(size.x, size.y, size.z, 0.1)
  baseZoomDistance = radius * 1.8
  controls.target.copy(center)
  controls.minDistance = baseZoomDistance / MAX_VIEW_ZOOM
  controls.maxDistance = baseZoomDistance / MIN_VIEW_ZOOM
  camera.position.set(center.x, center.y, center.z + baseZoomDistance / DEFAULT_VIEW_ZOOM)
  camera.near = Math.max(radius / 1000, 0.001)
  camera.far = Math.max(radius * 20, 10)
  camera.updateProjectionMatrix()
  controls.update()
  emitZoomChange(true)
}

function demoCloud() {
  // A torus-ish swirl so the viewer shows something before the bridge connects.
  const n = 8000
  const arr = new Float32Array(n * 3)
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 12
    const r = 0.6 + 0.25 * Math.sin(a * 0.5)
    arr[i * 3] = r * Math.cos(a) + (Math.random() - 0.5) * 0.05
    arr[i * 3 + 1] = r * Math.sin(a) + (Math.random() - 0.5) * 0.05
    arr[i * 3 + 2] = 0.3 * Math.sin(a * 0.25) + (Math.random() - 0.5) * 0.05
  }
  setPoints(arr)
}

function connectWs() {
  if (!props.wsUrl) {
    demoCloud()
    return
  }
  try {
    ws = new WebSocket(props.wsUrl)
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => {
      connected.value = true
      framedFirstCloud = false
    }
    ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        pendingFrame = ev.data
        requestRender()
      }
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

// Capture the current 3D view as a PNG data URL (for snapshots).
function snapshot(): string {
  flushPendingFrame(true)
  if (renderer && scene && camera) renderer.render(scene, camera)
  return renderer ? renderer.domElement.toDataURL('image/png') : ''
}

// Dolly the camera toward/away from the target (factor <1 zooms in, >1 out).
function zoomBy(factor: number) {
  if (!camera || !controls) return
  const target = controls.target
  camera.position.sub(target).multiplyScalar(factor).add(target)
  controls.update()
  emitZoomChange(true)
  requestRender()
}

function currentZoomFactor(): number | null {
  if (!camera || !controls || baseZoomDistance <= 0) return null
  const distance = camera.position.distanceTo(controls.target)
  if (distance <= 0) return null
  return Math.max(MIN_VIEW_ZOOM, Math.min(MAX_VIEW_ZOOM, baseZoomDistance / distance))
}

function emitZoomChange(force = false) {
  const zoom = currentZoomFactor()
  if (zoom === null) return
  if (!force && Math.abs(zoom - lastEmittedZoom) < 0.01) return
  lastEmittedZoom = zoom
  emit('zoom-change', zoom)
}

defineExpose({ snapshot, setPoints, zoomBy })

onMounted(() => {
  disposed = false
  initThree()
  connectWs()
  resizeObs = new ResizeObserver(() => {
    const el = container.value
    if (!el || !renderer || !camera) return
    camera.aspect = el.clientWidth / el.clientHeight
    camera.updateProjectionMatrix()
    renderer.setSize(el.clientWidth, el.clientHeight)
  })
  if (container.value) resizeObs.observe(container.value)
})

onBeforeUnmount(() => {
  disposed = true
  cancelAnimationFrame(raf)
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  ws?.close()
  ws = null
  pendingFrame = null
  controls?.removeEventListener('change', onControlsChange)
  resizeObs?.disconnect()
  controls?.dispose()
  geometry?.dispose()
  renderer?.dispose()
  if (renderer && container.value?.contains(renderer.domElement)) {
    container.value.removeChild(renderer.domElement)
  }
})
</script>

<template>
  <div class="pcv-root">
    <div ref="container" class="pcv-canvas pinch-zoom-surface" />
    <div class="pcv-status">
      <span :class="['pcv-dot', connected ? 'on' : 'off']" />
      {{ connected ? '深度相机已连接' : (wsUrl ? '等待深度相机…' : '') }}
      · {{ pointCount.toLocaleString() }} 点
    </div>
  </div>
</template>

<style scoped>
.pcv-root {
  position: relative;
  width: 100%;
  height: 100%;
  background: #0b0c0d;
}
.pcv-canvas {
  width: 100%;
  height: 100%;
  touch-action: none;
}
.pcv-status {
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
.pcv-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}
.pcv-dot.on {
  background: #24a148;
}
.pcv-dot.off {
  background: #da1e28;
}
</style>
