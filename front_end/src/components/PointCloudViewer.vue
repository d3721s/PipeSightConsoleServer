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

const container = ref<HTMLDivElement | null>(null)
const connected = ref(false)
const pointCount = ref(0)

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

function initThree() {
  const el = container.value!
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0b0c0d)

  camera = new THREE.PerspectiveCamera(60, el.clientWidth / el.clientHeight, 0.01, 1000)
  camera.position.set(0, 0, 2)

  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setSize(el.clientWidth, el.clientHeight)
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08

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

  animate()
}

function animate() {
  raf = requestAnimationFrame(animate)
  controls?.update()
  if (renderer && scene && camera) renderer.render(scene, camera)
}

// Replace the point cloud. `xyz` is a flat Float32Array [x,y,z, x,y,z, ...].
function setPoints(xyz: Float32Array) {
  if (!geometry) return
  const count = Math.floor(xyz.length / 3)
  pointCount.value = count

  // Color points by depth (z) for readability.
  const colors = new Float32Array(count * 3)
  let zmin = Infinity
  let zmax = -Infinity
  for (let i = 0; i < count; i++) {
    const z = xyz[i * 3 + 2]
    if (z < zmin) zmin = z
    if (z > zmax) zmax = z
  }
  const span = zmax - zmin || 1
  const color = new THREE.Color()
  for (let i = 0; i < count; i++) {
    const t = (xyz[i * 3 + 2] - zmin) / span
    color.setHSL(0.7 - 0.7 * t, 0.9, 0.5) // blue(far) -> red(near)
    colors[i * 3] = color.r
    colors[i * 3 + 1] = color.g
    colors[i * 3 + 2] = color.b
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(xyz, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.computeBoundingSphere()
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
  controls.target.copy(center)
  camera.position.set(center.x, center.y, center.z + radius * 1.8)
  camera.near = Math.max(radius / 1000, 0.001)
  camera.far = Math.max(radius * 20, 10)
  camera.updateProjectionMatrix()
  controls.update()
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
      const buf = ev.data as ArrayBuffer
      if (buf.byteLength < 8) return
      const view = new DataView(buf)
      // magic "PCD1"
      if (view.getUint8(0) !== 0x50 || view.getUint8(1) !== 0x43) return
      const count = view.getUint32(4, true)
      const expected = 8 + count * 3 * 4
      if (buf.byteLength < expected) return
      const xyz = new Float32Array(buf, 8, count * 3)
      // Copy out (the view is backed by the socket buffer).
      setPoints(new Float32Array(xyz))
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

// Capture the current 3D view as a PNG data URL (for snapshots).
function snapshot(): string {
  if (renderer && scene && camera) renderer.render(scene, camera)
  return renderer ? renderer.domElement.toDataURL('image/png') : ''
}

// Dolly the camera toward/away from the target (factor <1 zooms in, >1 out).
function zoomBy(factor: number) {
  if (!camera || !controls) return
  const target = controls.target
  camera.position.sub(target).multiplyScalar(factor).add(target)
  controls.update()
}

defineExpose({ snapshot, setPoints, zoomBy })

onMounted(() => {
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
  cancelAnimationFrame(raf)
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
  ws?.close()
  ws = null
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
    <div ref="container" class="pcv-canvas" />
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
