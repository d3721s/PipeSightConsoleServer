<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  distance: number
  projectName: string
  location: string
  // Whether the cart odometer is connected; when false the backend burns
  // "距离: --", so we mirror that here.
  odometerConnected?: boolean
}>()

// Live clock. Mirrors the backend ffmpeg drawtext format exactly:
//   时间: %Y-%m-%d %H:%M:%S   (zero-padded, 24h, halfwidth colon)
const now = ref(new Date())
let timer: number | null = null
onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 1000)
})
onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
})

const pad = (n: number) => String(n).padStart(2, '0')
const timeText = computed(() => {
  const d = now.value
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

// Backend: "距离: --" when no odometer, else "距离: 12.34m" (no space before m).
const distanceText = computed(() =>
  props.odometerConnected === false ? '--' : `${props.distance.toFixed(2)}m`
)

// Backend uses `name or "-"` / `location or "-"`.
const nameText = computed(() => props.projectName || '-')
const locationText = computed(() => props.location || '-')
</script>

<template>
  <div class="osd-overlay">
    <div class="osd-line">时间: {{ timeText }}</div>
    <div class="osd-line">距离: {{ distanceText }}</div>
    <div class="osd-line">项目名称: {{ nameText }}</div>
    <div class="osd-line">项目地点: {{ locationText }}</div>
  </div>
</template>

<style scoped>
/* Mirror the burned-in OSD: yellow text on a translucent black box, matching
   ffmpeg drawtext (fontcolor=yellow, box=1, boxcolor=black@0.4). */
.osd-overlay {
  position: absolute;
  top: 1.25rem;
  left: 1.25rem;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
}
.osd-line {
  background: rgba(0, 0, 0, 0.4);
  color: #ffff00;
  font-size: 1rem;
  line-height: 1.3;
  padding: 0.1rem 0.4rem;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
