<script setup lang="ts">
import { CvButton } from '@carbon/vue'
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
    <div class="switcher-row">
      <cv-button
        size="field"
        :kind="device === 'front' ? 'primary' : 'tertiary'"
        @click="emit('select-device', 'front')"
      >前摄</cv-button>
      <cv-button
        size="field"
        :kind="device === 'rear' ? 'primary' : 'tertiary'"
        @click="emit('select-device', 'rear')"
      >后摄</cv-button>
    </div>
    <div class="switcher-row">
      <cv-button
        size="field"
        :kind="channel === 1 ? 'primary' : 'tertiary'"
        @click="emit('select-channel', 1)"
      >云台</cv-button>
      <cv-button
        size="field"
        :kind="channel === 2 ? 'primary' : 'tertiary'"
        @click="emit('select-channel', 2)"
      >固定</cv-button>
    </div>
  </div>
</template>

<style scoped>
.switcher-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.switcher-row {
  display: flex;
  gap: 0.25rem;
}
.switcher-row :deep(.cv-button) {
  flex: 1;
}
</style>
