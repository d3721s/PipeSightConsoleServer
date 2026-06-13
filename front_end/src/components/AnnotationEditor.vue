<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'

type Tool = 'select' | 'pen' | 'rect' | 'text'

interface RectShape {
  kind: 'rect'
  x: number
  y: number
  w: number
  h: number
  color: string
}
interface TextShape {
  kind: 'text'
  x: number
  y: number
  text: string
  color: string
}
interface PathShape {
  kind: 'path'
  points: number[][]
  color: string
}
type Shape = RectShape | TextShape | PathShape

const props = defineProps<{
  baseImage: string // URL or data URL of the background image / captured frame
}>()

const emit = defineEmits<{
  (e: 'save', payload: { shapes: Shape[]; baseSize: { w: number; h: number }; renderedPng: string; defect: Record<string, unknown> }): void
  (e: 'cancel'): void
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
const tool = ref<Tool>('rect')
const color = ref('#ff3030')
const shapes = ref<Shape[]>([])
const selectedIndex = ref(-1)
const baseSize = reactive({ w: 0, h: 0 })

const defect = reactive({
  defectType: '',
  defectCode: '',
  severity: '',
  direction: '',
  position: '',
  note: '',
  distanceM: 0
})

let img = new Image()
let drawing = false
let startX = 0
let startY = 0
let draftRect: RectShape | null = null
let draftPath: PathShape | null = null
let dragOffsetX = 0
let dragOffsetY = 0

function loadBase() {
  img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    baseSize.w = img.naturalWidth
    baseSize.h = img.naturalHeight
    const c = canvas.value
    if (c) {
      c.width = baseSize.w
      c.height = baseSize.h
    }
    redraw()
  }
  img.src = props.baseImage
}

function toImageCoords(event: PointerEvent): { x: number; y: number } {
  const c = canvas.value!
  const rect = c.getBoundingClientRect()
  return {
    x: ((event.clientX - rect.left) / rect.width) * c.width,
    y: ((event.clientY - rect.top) / rect.height) * c.height
  }
}

function drawShape(ctx: CanvasRenderingContext2D, shape: Shape, selected: boolean) {
  ctx.lineWidth = Math.max(2, baseSize.w / 500)
  ctx.strokeStyle = shape.color
  ctx.fillStyle = shape.color
  if (shape.kind === 'rect') {
    ctx.strokeRect(shape.x, shape.y, shape.w, shape.h)
    if (selected) {
      ctx.setLineDash([6, 4])
      ctx.strokeStyle = '#1f6feb'
      ctx.strokeRect(shape.x - 2, shape.y - 2, shape.w + 4, shape.h + 4)
      ctx.setLineDash([])
    }
  } else if (shape.kind === 'text') {
    const size = Math.max(20, baseSize.w / 40)
    ctx.font = `${size}px sans-serif`
    ctx.textBaseline = 'top'
    ctx.fillText(shape.text, shape.x, shape.y)
    if (selected) {
      const width = ctx.measureText(shape.text).width
      ctx.setLineDash([6, 4])
      ctx.strokeStyle = '#1f6feb'
      ctx.strokeRect(shape.x - 2, shape.y - 2, width + 4, size + 4)
      ctx.setLineDash([])
    }
  } else {
    ctx.beginPath()
    shape.points.forEach((p, i) => (i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])))
    ctx.stroke()
  }
}

function redraw() {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, c.width, c.height)
  if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, c.width, c.height)
  shapes.value.forEach((shape, i) => drawShape(ctx, shape, i === selectedIndex.value && tool.value === 'select'))
  if (draftRect) drawShape(ctx, draftRect, false)
  if (draftPath) drawShape(ctx, draftPath, false)
}

function shapeBounds(shape: Shape): { x: number; y: number; w: number; h: number } {
  if (shape.kind === 'rect') return { x: shape.x, y: shape.y, w: shape.w, h: shape.h }
  if (shape.kind === 'text') {
    const size = Math.max(20, baseSize.w / 40)
    return { x: shape.x, y: shape.y, w: size * Math.max(1, shape.text.length) * 0.6, h: size }
  }
  const xs = shape.points.map((p) => p[0])
  const ys = shape.points.map((p) => p[1])
  return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }
}

function hitTest(x: number, y: number): number {
  // Topmost shape under the point (normalize negative w/h for rects).
  for (let i = shapes.value.length - 1; i >= 0; i--) {
    const b = shapeBounds(shapes.value[i])
    const x0 = Math.min(b.x, b.x + b.w)
    const y0 = Math.min(b.y, b.y + b.h)
    if (x >= x0 - 6 && x <= x0 + Math.abs(b.w) + 6 && y >= y0 - 6 && y <= y0 + Math.abs(b.h) + 6) return i
  }
  return -1
}

function onPointerDown(event: PointerEvent) {
  const c = canvas.value!
  c.setPointerCapture(event.pointerId)
  const { x, y } = toImageCoords(event)
  startX = x
  startY = y

  if (tool.value === 'select') {
    selectedIndex.value = hitTest(x, y)
    if (selectedIndex.value >= 0) {
      const b = shapeBounds(shapes.value[selectedIndex.value])
      dragOffsetX = x - b.x
      dragOffsetY = y - b.y
      drawing = true
    }
    redraw()
    return
  }
  if (tool.value === 'rect') {
    draftRect = { kind: 'rect', x, y, w: 0, h: 0, color: color.value }
    drawing = true
  } else if (tool.value === 'pen') {
    draftPath = { kind: 'path', points: [[x, y]], color: color.value }
    drawing = true
  } else if (tool.value === 'text') {
    const text = window.prompt('输入文字')
    if (text && text.trim()) {
      shapes.value.push({ kind: 'text', x, y, text: text.trim(), color: color.value })
      redraw()
    }
  }
}

function onPointerMove(event: PointerEvent) {
  if (!drawing) return
  const { x, y } = toImageCoords(event)
  if (tool.value === 'select' && selectedIndex.value >= 0) {
    moveShape(shapes.value[selectedIndex.value], x - dragOffsetX, y - dragOffsetY)
    redraw()
  } else if (draftRect) {
    draftRect.w = x - startX
    draftRect.h = y - startY
    redraw()
  } else if (draftPath) {
    draftPath.points.push([x, y])
    redraw()
  }
}

function onPointerUp() {
  if (draftRect) {
    if (Math.abs(draftRect.w) > 3 && Math.abs(draftRect.h) > 3) {
      // Normalize so w/h are positive.
      if (draftRect.w < 0) {
        draftRect.x += draftRect.w
        draftRect.w = -draftRect.w
      }
      if (draftRect.h < 0) {
        draftRect.y += draftRect.h
        draftRect.h = -draftRect.h
      }
      shapes.value.push(draftRect)
    }
    draftRect = null
  }
  if (draftPath) {
    if (draftPath.points.length > 1) shapes.value.push(draftPath)
    draftPath = null
  }
  drawing = false
  redraw()
}

function moveShape(shape: Shape, x: number, y: number) {
  if (shape.kind === 'rect' || shape.kind === 'text') {
    shape.x = x
    shape.y = y
  } else {
    const b = shapeBounds(shape)
    const dx = x - b.x
    const dy = y - b.y
    shape.points = shape.points.map((p) => [p[0] + dx, p[1] + dy])
  }
}

function undo() {
  shapes.value.pop()
  selectedIndex.value = -1
  redraw()
}

function clearAll() {
  shapes.value = []
  selectedIndex.value = -1
  redraw()
}

function deleteSelected() {
  if (selectedIndex.value >= 0) {
    shapes.value.splice(selectedIndex.value, 1)
    selectedIndex.value = -1
    redraw()
  }
}

function renderPng(): string {
  const off = document.createElement('canvas')
  off.width = baseSize.w
  off.height = baseSize.h
  const ctx = off.getContext('2d')!
  if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, off.width, off.height)
  shapes.value.forEach((shape) => drawShape(ctx, shape, false))
  return off.toDataURL('image/png')
}

function save() {
  emit('save', {
    shapes: shapes.value,
    baseSize: { w: baseSize.w, h: baseSize.h },
    renderedPng: renderPng(),
    defect: { ...defect }
  })
}

watch(() => props.baseImage, loadBase)
onMounted(loadBase)
</script>

<template>
  <div class="annot-editor">
    <div class="annot-toolbar">
      <button :class="{ active: tool === 'select' }" @click="tool = 'select'">选择</button>
      <button :class="{ active: tool === 'pen' }" @click="tool = 'pen'">画笔</button>
      <button :class="{ active: tool === 'rect' }" @click="tool = 'rect'">标记框</button>
      <button :class="{ active: tool === 'text' }" @click="tool = 'text'">文字</button>
      <button @click="undo">撤销</button>
      <button @click="clearAll">清空</button>
      <button v-if="tool === 'select' && selectedIndex >= 0" class="danger" @click="deleteSelected">删除选中</button>
      <label class="annot-color"><span>颜色</span><input v-model="color" type="color" /></label>
    </div>

    <div class="annot-canvas-wrap">
      <canvas
        ref="canvas"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      />
    </div>

    <div class="annot-form">
      <label><span>缺陷类型</span><input v-model="defect.defectType" /></label>
      <label><span>缺陷代码</span><input v-model="defect.defectCode" /></label>
      <label><span>等级</span><input v-model="defect.severity" /></label>
      <label><span>方向</span><input v-model="defect.direction" placeholder="如 3点钟" /></label>
      <label><span>位置</span><input v-model="defect.position" /></label>
      <label><span>里程 m</span><input v-model.number="defect.distanceM" type="number" step="0.01" /></label>
      <label class="annot-note"><span>备注</span><input v-model="defect.note" /></label>
    </div>

    <div class="annot-actions">
      <button class="primary-action" @click="save">标记并保存</button>
      <button @click="$emit('cancel')">取消</button>
    </div>
  </div>
</template>
