<script setup lang="ts">
import { CaretUp24, CaretDown24, CaretLeft24, CaretRight24 } from '@carbon/icons-vue'
import type { PtzDirection } from '../ws'

const props = defineProps<{
  disabled: boolean
}>()

const emit = defineEmits<{
  (e: 'step', direction: PtzDirection): void
  (e: 'start', direction: PtzDirection): void
  (e: 'stop'): void
}>()

// Short press => single step; hold > 250ms => continuous move until release.
const HOLD_MS = 250
let holdTimer: number | null = null
let didHold = false

function onDown(direction: PtzDirection) {
  if (props.disabled) return
  didHold = false
  holdTimer = window.setTimeout(() => {
    didHold = true
    emit('start', direction)
  }, HOLD_MS)
}

function onUp(direction: PtzDirection) {
  if (props.disabled) return
  if (holdTimer !== null) {
    window.clearTimeout(holdTimer)
    holdTimer = null
  }
  if (didHold) {
    emit('stop')
  } else {
    emit('step', direction)
  }
  didHold = false
}

function onLeave() {
  // Pointer left the button mid-hold: stop continuous move, cancel pending step.
  if (holdTimer !== null) {
    window.clearTimeout(holdTimer)
    holdTimer = null
  }
  if (didHold) emit('stop')
  didHold = false
}
</script>

<template>
  <div class="ptz-pad" :class="{ disabled }">
    <button
      class="ptz-btn up"
      type="button"
      :disabled="disabled"
      @pointerdown.prevent="onDown('up')"
      @pointerup="onUp('up')"
      @pointerleave="onLeave"
      @pointercancel="onLeave"
    >
      <caret-up24 />
    </button>
    <button
      class="ptz-btn left"
      type="button"
      :disabled="disabled"
      @pointerdown.prevent="onDown('left')"
      @pointerup="onUp('left')"
      @pointerleave="onLeave"
      @pointercancel="onLeave"
    >
      <caret-left24 />
    </button>
    <span class="ptz-hub" />
    <button
      class="ptz-btn right"
      type="button"
      :disabled="disabled"
      @pointerdown.prevent="onDown('right')"
      @pointerup="onUp('right')"
      @pointerleave="onLeave"
      @pointercancel="onLeave"
    >
      <caret-right24 />
    </button>
    <button
      class="ptz-btn down"
      type="button"
      :disabled="disabled"
      @pointerdown.prevent="onDown('down')"
      @pointerup="onUp('down')"
      @pointerleave="onLeave"
      @pointercancel="onLeave"
    >
      <caret-down24 />
    </button>
  </div>
</template>

<style scoped>
.ptz-pad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(3, 1fr);
  gap: 4px;
  width: 9.5rem;
  height: 9.5rem;
}
.ptz-pad.disabled {
  opacity: 0.4;
}
.ptz-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(22, 22, 22, 0.78);
  color: #f4f4f4;
  border: 1px solid #525252;
  cursor: pointer;
  touch-action: none;
}
.ptz-btn:not(:disabled):active {
  background: #0f62fe;
  border-color: #0f62fe;
}
.ptz-btn:disabled {
  cursor: not-allowed;
}
.ptz-btn.up {
  grid-column: 2;
  grid-row: 1;
  border-radius: 6px 6px 0 0;
}
.ptz-btn.left {
  grid-column: 1;
  grid-row: 2;
  border-radius: 6px 0 0 6px;
}
.ptz-btn.right {
  grid-column: 3;
  grid-row: 2;
  border-radius: 0 6px 6px 0;
}
.ptz-btn.down {
  grid-column: 2;
  grid-row: 3;
  border-radius: 0 0 6px 6px;
}
.ptz-hub {
  grid-column: 2;
  grid-row: 2;
  border-radius: 50%;
  background: rgba(22, 22, 22, 0.5);
  border: 1px solid #525252;
}
</style>
