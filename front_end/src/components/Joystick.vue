<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    // Output magnitude range; the cart's 485 joystick wants -800..800.
    range?: number
    disabled?: boolean
  }>(),
  { range: 800, disabled: false }
)

// Emits the joystick vector. x = horizontal (right +), y = vertical (forward +).
const emit = defineEmits<{
  (e: 'move', payload: { x: number; y: number }): void
}>()

const base = ref<HTMLDivElement | null>(null)
const handleX = ref(0) // px offset from center
const handleY = ref(0)
const active = ref(false)
let radius = 1
let lastEmit = 0
const EMIT_INTERVAL = 50 // ms; matches the controller's recommended 50ms refresh

function clampToCircle(dx: number, dy: number): { x: number; y: number } {
  const dist = Math.hypot(dx, dy)
  if (dist <= radius) return { x: dx, y: dy }
  const k = radius / dist
  return { x: dx * k, y: dy * k }
}

function emitVector(throttled: boolean) {
  // Normalize handle px -> [-range, range]. Screen Y is down, so negate for
  // "forward = positive".
  const x = Math.round((handleX.value / radius) * props.range)
  const y = Math.round((-handleY.value / radius) * props.range)
  if (throttled) {
    const now = performance.now()
    if (now - lastEmit < EMIT_INTERVAL) return
    lastEmit = now
  }
  emit('move', { x, y })
}

function onDown(event: PointerEvent) {
  if (props.disabled || !base.value) return
  const rect = base.value.getBoundingClientRect()
  radius = rect.width / 2
  active.value = true
  lastEmit = 0
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  moveTo(event)
  emitVector(false)
}

function moveTo(event: PointerEvent) {
  if (!base.value) return
  const rect = base.value.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const { x, y } = clampToCircle(event.clientX - cx, event.clientY - cy)
  handleX.value = x
  handleY.value = y
}

function onMove(event: PointerEvent) {
  if (!active.value) return
  moveTo(event)
  emitVector(true)
}

function onUp(event: PointerEvent) {
  if (!active.value) return
  active.value = false
  try {
    ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  } catch {
    // already released
  }
  // Recenter and command stop.
  handleX.value = 0
  handleY.value = 0
  emit('move', { x: 0, y: 0 })
}

onBeforeUnmount(() => {
  if (active.value) emit('move', { x: 0, y: 0 })
})
</script>

<template>
  <div class="joystick" :class="{ disabled }">
    <span class="joystick-title">底盘控制</span>
    <div
      ref="base"
      class="joystick-base"
      @pointerdown="onDown"
      @pointermove="onMove"
      @pointerup="onUp"
      @pointercancel="onUp"
    >
      <span class="joystick-ring" />
      <span class="joystick-cross-h" />
      <span class="joystick-cross-v" />
      <span
        class="joystick-handle"
        :class="{ active }"
        :style="{ transform: `translate(calc(-50% + ${handleX}px), calc(-50% + ${handleY}px))` }"
      />
    </div>
  </div>
</template>

<style scoped>
.joystick {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.375rem;
  user-select: none;
}
.joystick.disabled {
  opacity: 0.4;
  pointer-events: none;
}
.joystick-title {
  color: #c6c6c6;
  font-size: 0.75rem;
  background: rgba(22, 22, 22, 0.7);
  padding: 0.125rem 0.5rem;
  border-radius: 2px;
}
.joystick-base {
  position: relative;
  width: 9.5rem;
  height: 9.5rem;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 45%, #2a2a2a, #161616);
  border: 1px solid #525252;
  touch-action: none;
  cursor: grab;
}
.joystick-base:active {
  cursor: grabbing;
}
.joystick-ring {
  position: absolute;
  inset: 18%;
  border: 1px dashed #4d4d4d;
  border-radius: 50%;
  pointer-events: none;
}
.joystick-cross-h,
.joystick-cross-v {
  position: absolute;
  background: #393939;
  pointer-events: none;
}
.joystick-cross-h {
  left: 12%;
  right: 12%;
  top: 50%;
  height: 1px;
}
.joystick-cross-v {
  top: 12%;
  bottom: 12%;
  left: 50%;
  width: 1px;
}
.joystick-handle {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  background: #0f62fe;
  border: 2px solid #4589ff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
  pointer-events: none;
}
.joystick-handle.active {
  background: #4589ff;
}
</style>
