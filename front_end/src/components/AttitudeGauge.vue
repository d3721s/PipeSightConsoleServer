<script setup lang="ts">
import { computed, useId } from 'vue'

// A round attitude-indicator ("水平仪") for one Euler angle, paired with its
// numeric value: an artificial horizon that banks (rotates) with the angle.
const props = defineProps<{
  value: number | null
  label: string
}>()

// Unique clip-path id so several gauges on one page don't collide.
const clipId = useId()

const hasValue = computed(() => props.value !== null && Number.isFinite(props.value))
const display = computed(() => (hasValue.value ? `${(props.value as number).toFixed(1)}°` : '--'))

// Bank rotates the horizon the opposite way the chassis tilts.
const rollRotation = computed(() => (hasValue.value ? -(props.value as number) : 0))

// Bank scale marks around the top of the dial (degrees from 12 o'clock).
const rollTicks = [-60, -30, 0, 30, 60].map(a => {
  const rad = (a * Math.PI) / 180
  const inner = a === 0 ? 36 : 40
  return {
    a,
    x1: 50 + inner * Math.sin(rad),
    y1: 50 - inner * Math.cos(rad),
    x2: 50 + 46 * Math.sin(rad),
    y2: 50 - 46 * Math.cos(rad)
  }
})
</script>

<template>
  <div class="att-gauge" :class="{ stale: !hasValue }">
    <svg class="att-svg" viewBox="0 0 100 100" aria-hidden="true">
      <defs>
        <clipPath :id="clipId"><circle cx="50" cy="50" r="46" /></clipPath>
      </defs>

      <!-- Dial backdrop (shows through if a band is clamped off-screen). -->
      <circle cx="50" cy="50" r="46" fill="#1b2733" />

      <!-- Sky/ground disc that banks with the roll angle. -->
      <g :clip-path="`url(#${clipId})`">
        <g class="att-move" :transform="`rotate(${rollRotation} 50 50)`">
          <rect x="-60" y="-60" width="220" height="110" fill="#3f6fc4" />
          <rect x="-60" y="50" width="220" height="110" fill="#5b7a3a" />
          <line x1="-60" y1="50" x2="160" y2="50" stroke="#fff" stroke-width="1.4" />
          <line
            v-for="t in rollTicks"
            :key="t.a"
            :x1="t.x1"
            :y1="t.y1"
            :x2="t.x2"
            :y2="t.y2"
            stroke="#fff"
            stroke-width="1.2"
          />
        </g>
      </g>

      <!-- Bezel. -->
      <circle cx="50" cy="50" r="46" fill="none" stroke="#6f6f6f" stroke-width="2.5" />

      <!-- Fixed aircraft reference + top pointer. -->
      <g>
        <line x1="28" y1="50" x2="43" y2="50" stroke="#f1c21b" stroke-width="2.4" />
        <line x1="57" y1="50" x2="72" y2="50" stroke="#f1c21b" stroke-width="2.4" />
        <circle cx="50" cy="50" r="1.8" fill="#f1c21b" />
        <polygon points="50,5 46,13 54,13" fill="#f1c21b" />
      </g>
    </svg>

    <div class="att-text">
      <span class="att-label">{{ label }}</span>
      <span class="att-value">{{ display }}</span>
    </div>
  </div>
</template>

<style scoped>
.att-gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
}
.att-gauge.stale {
  opacity: 0.5;
}
.att-svg {
  width: 3.5rem;
  height: 3.5rem;
  flex: 0 0 auto;
}
/* Ease the 400ms telemetry steps so the dials glide instead of jumping. */
.att-move {
  transition: transform 0.35s ease-out;
}
.att-text {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
  min-width: 0;
  text-align: center;
}
.att-label {
  color: #8d8d8d;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.att-value {
  color: #f4f4f4;
  font-size: 1.25rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
</style>
