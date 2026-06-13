<script setup lang="ts">
import type { CameraCode } from '../types'

defineProps<{
  device: CameraCode
  channel: number
}>()

const emit = defineEmits<{
  (e: 'select-device', device: CameraCode): void
  (e: 'select-channel', channel: number): void
}>()
</script>

<template>
  <div class="switcher-group">
    <!-- Device: front / rear — mutually exclusive segmented toggle -->
    <div class="segmented">
      <button
        type="button"
        class="seg-btn"
        :class="{ active: device === 'front' }"
        @click="emit('select-device', 'front')"
      >前摄</button>
      <button
        type="button"
        class="seg-btn"
        :class="{ active: device === 'rear' }"
        @click="emit('select-device', 'rear')"
      >后摄</button>
    </div>

    <!-- Channel: ptz / fixed — mutually exclusive segmented toggle -->
    <div class="segmented">
      <button
        type="button"
        class="seg-btn"
        :class="{ active: channel === 1 }"
        @click="emit('select-channel', 1)"
      >云台</button>
      <button
        type="button"
        class="seg-btn"
        :class="{ active: channel === 2 }"
        @click="emit('select-channel', 2)"
      >固定</button>
    </div>
  </div>
</template>

<style scoped>
.switcher-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
/* Segmented control: buttons joined edge-to-edge; exactly one is active. */
.segmented {
  display: flex;
  border: 1px solid #4d4d4d;
  border-radius: 4px;
  overflow: hidden;
}
.seg-btn {
  flex: 1;
  padding: 0.625rem 0.5rem;
  font-size: 0.9375rem;
  background: #2a2a2a;
  color: #c6c6c6;
  border: none;
  border-left: 1px solid #4d4d4d;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  white-space: nowrap;
}
.seg-btn:first-child {
  border-left: none;
}
.seg-btn:hover:not(.active) {
  background: #393939;
  color: #f4f4f4;
}
.seg-btn.active {
  background: #0f62fe;
  color: #ffffff;
  font-weight: 600;
}
</style>
