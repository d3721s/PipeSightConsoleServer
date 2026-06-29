<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { CvButton, CvTextInput } from '@carbon/vue'
import { Cursor_124, Pen24, Crop24, TextScale24, Undo24, TrashCan24, Calculator24, Maximize24, Minimize24 } from '@carbon/icons-vue'
import { measureRectArea, formatArea, type DepthFrame } from '../utils/depthArea'

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
  initialLeftMileage?: number | null
  initialRightMileage?: number | null
  // When set (depth snapshots), enables area measurement: the selected rectangle
  // is measured against this depth frame and the area saved with the annotation.
  depthFrame?: DepthFrame | null
  // Whether the parent page is in maximize (rail collapsed) mode; drives the
  // toolbar toggle icon/label. The parent owns the actual layout switch.
  maximized?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: { shapes: Shape[]; baseSize: { w: number; h: number }; renderedPng: string; defect: Record<string, unknown> }): void
  (e: 'cancel'): void
  (e: 'toggle-maximize'): void
}>()

const measureMode = () => !!props.depthFrame
const areaM2 = ref<number | null>(null)
const areaText = ref<string | null>(null)

const canvas = ref<HTMLCanvasElement | null>(null)
const tool = ref<Tool>('rect')
const color = ref('#ff3030')
const shapes = ref<Shape[]>([])
const selectedIndex = ref(-1)
const baseSize = reactive({ w: 0, h: 0 })

function toFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function initialMileageValue(value: number | null | undefined): number | null {
  return toFiniteNumber(value)
}

const defect = reactive({
  defectType: '',
  defectCode: '',
  severity: '',
  direction: '',
  position: '',
  note: '',
  leftMileage: initialMileageValue(props.initialLeftMileage),
  rightMileage: initialMileageValue(props.initialRightMileage)
})

const tools: { id: Tool; label: string; icon: unknown }[] = [
  { id: 'select', label: '选择', icon: Cursor_124 },
  { id: 'pen', label: '画笔', icon: Pen24 },
  { id: 'rect', label: '矩形', icon: Crop24 },
  { id: 'text', label: '文字', icon: TextScale24 }
]

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
      // In measure mode, the latest rectangle defines the region to measure.
      if (measureMode()) measureArea(draftRect)
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

// Measure the real surface area of a rectangle against the depth frame. The
// annotation canvas uses the image's pixel space (baseSize); if the depth frame
// resolution differs, scale rect coords into depth-frame pixels first.
function measureArea(rect: RectShape) {
  const frame = props.depthFrame
  if (!frame) return
  const sx = baseSize.w ? frame.width / baseSize.w : 1
  const sy = baseSize.h ? frame.height / baseSize.h : 1
  const x0 = Math.round(rect.x * sx)
  const y0 = Math.round(rect.y * sy)
  const x1 = Math.round((rect.x + rect.w) * sx)
  const y1 = Math.round((rect.y + rect.h) * sy)
  const result = measureRectArea(frame, x0, y0, x1, y1)
  if (!result || result.triangles === 0) {
    areaM2.value = null
    areaText.value = '该区域无有效深度'
    return
  }
  areaM2.value = result.areaM2
  areaText.value = formatArea(result.areaM2)
}

function save() {
  const leftMileage = toFiniteNumber(defect.leftMileage)
  const rightMileage = toFiniteNumber(defect.rightMileage)
  emit('save', {
    shapes: shapes.value,
    baseSize: { w: baseSize.w, h: baseSize.h },
    renderedPng: renderPng(),
    defect: {
      ...defect,
      leftMileage,
      rightMileage,
      ...(measureMode() ? { areaM2: areaM2.value } : {})
    }
  })
}

watch(() => props.baseImage, () => {
  // New base image -> reset the measurement readout.
  areaM2.value = null
  areaText.value = null
  loadBase()
})
watch(() => [props.initialLeftMileage, props.initialRightMileage], () => {
  defect.leftMileage = initialMileageValue(props.initialLeftMileage)
  defect.rightMileage = initialMileageValue(props.initialRightMileage)
})
onMounted(() => {
  if (measureMode()) tool.value = 'rect' // area measurement is rectangle-based
  loadBase()
})
</script>

<template>
  <div class="annot-editor">
    <div class="annot-toolbar">
      <div class="tool-segmented">
        <button
          v-for="t in tools"
          :key="t.id"
          type="button"
          class="tool-btn"
          :class="{ active: tool === t.id }"
          @click="tool = t.id"
        >
          <component :is="t.icon" class="tool-icon" />
          <span>{{ t.label }}</span>
        </button>
      </div>
      <div class="annot-tools">
        <cv-button size="sm" kind="ghost" :icon="Undo24" @click="undo">撤销</cv-button>
        <cv-button size="sm" kind="ghost" :icon="TrashCan24" @click="clearAll">清空</cv-button>
        <cv-button
          v-if="tool === 'select' && selectedIndex >= 0"
          size="sm"
          kind="danger--ghost"
          @click="deleteSelected"
        >删除选中</cv-button>
        <cv-button
          size="sm"
          kind="ghost"
          :icon="maximized ? Minimize24 : Maximize24"
          @click="emit('toggle-maximize')"
        >{{ maximized ? '还原' : '最大化' }}</cv-button>
        <label class="annot-color"><span>颜色</span><input v-model="color" type="color" /></label>
        <div v-if="depthFrame" class="annot-area">
          <component :is="Calculator24" class="annot-area-icon" />
          <span v-if="areaText" class="annot-area-value">{{ areaText }}</span>
          <span v-else class="annot-area-hint">框选区域以测量面积</span>
        </div>
      </div>
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
      <cv-text-input v-model="defect.defectType" label="缺陷类型" />
      <cv-text-input v-model="defect.defectCode" label="缺陷代码" />
      <cv-text-input v-model="defect.severity" label="等级" />
      <cv-text-input v-model="defect.direction" label="方向" placeholder="如 3点钟" />
      <cv-text-input v-model="defect.position" label="位置" />
      <cv-text-input v-model="defect.note" label="备注" class="annot-note" />
    </div>

    <div class="annot-actions">
      <cv-button kind="secondary" @click="emit('cancel')">取消</cv-button>
      <cv-button @click="save">标记并保存</cv-button>
    </div>
  </div>
</template>

<style scoped>
.annot-editor {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  /* Fill the annotate-main column so the canvas area can flex-grow into the
     space left by the toolbar / form / actions instead of being a small box. */
  height: 100%;
  min-height: 0;
}
.annot-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #e0e0e0;
}
.annot-tools {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
/* Tool picker: mutually-exclusive segmented control (select / pen / rect / text). */
.tool-segmented {
  display: flex;
  border: 1px solid #c6c6c6;
  border-radius: 4px;
  overflow: hidden;
}
.tool-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.9375rem;
  background: #ffffff;
  color: #393939;
  border: none;
  border-left: 1px solid #c6c6c6;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  white-space: nowrap;
}
.tool-btn:first-child {
  border-left: none;
}
.tool-btn:hover:not(.active) {
  background: #e8e8e8;
}
.tool-btn.active {
  background: #0f62fe;
  color: #ffffff;
  font-weight: 600;
}
.tool-icon {
  width: 1.125rem;
  height: 1.125rem;
}
.annot-color {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: #525252;
  font-size: 0.75rem;
  padding-left: 0.5rem;
}
.annot-color input {
  width: 2rem;
  height: 1.75rem;
  border: none;
  background: none;
  padding: 0;
}
.annot-area {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding-left: 0.5rem;
  border-left: 1px solid #e0e0e0;
}
.annot-area-icon {
  width: 1.125rem;
  height: 1.125rem;
  color: #0f62fe;
}
.annot-area-value {
  color: #0f62fe;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.annot-area-hint {
  color: #6f6f6f;
  font-size: 0.8125rem;
}
.annot-canvas-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  background: #000;
  border: 1px solid #e0e0e0;
  /* Grow to fill the available height; keep a sensible floor and a generous
     ceiling so the image gets as much room as the layout allows. */
  flex: 1 1 auto;
  min-height: 20rem;
  max-height: 78vh;
  overflow: hidden;
}
.annot-canvas-wrap canvas {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  touch-action: none;
  cursor: crosshair;
}
.annot-form {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem 1rem;
}
.annot-note {
  grid-column: 1 / -1;
}
.annot-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
