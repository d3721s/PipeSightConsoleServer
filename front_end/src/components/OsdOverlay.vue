<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { formatWheelMileage } from '../utils/osd'

defineProps<{
  leftMileage: number | null
  rightMileage: number | null
  projectName: string
  location: string
}>()

// Live clock for the OSD readout.
const now = ref(new Date())
let timer: number | null = null
onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 1000)
})
onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<template>
  <div class="osd-overlay">
    <div class="osd-line">时间：{{ now.toLocaleString() }}</div>
    <div class="osd-line">距离：{{ formatWheelMileage(leftMileage, rightMileage) }}</div>
    <div class="osd-line">项目名称：{{ projectName || '未创建项目' }}</div>
    <div class="osd-line">地点：{{ location || '-' }}</div>
  </div>
</template>

<style scoped>
.osd-overlay {
  position: absolute;
  top: 1rem;
  left: 1rem;
  padding: 0.5rem 0.75rem;
  background: rgba(0, 0, 0, 0.45);
  border-left: 3px solid #0f62fe;
  color: #f4f4f4;
  font-size: 0.8125rem;
  line-height: 1.45;
  pointer-events: none;
  border-radius: 2px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}
</style>
