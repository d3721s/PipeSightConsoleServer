<script setup lang="ts">
import { computed, useId } from 'vue'

// A round attitude-indicator ("水平仪") for one Euler angle, paired with its
// numeric value. Three modes:
//   roll  — artificial horizon that banks (rotates) with the roll angle
//   pitch — artificial horizon that climbs/dives (translates) with a pitch ladder
//   yaw   — compass rose with a heading needle
const props = defineProps<{
  mode: 'roll' | 'pitch' | 'yaw'
  value: number | null
  label: string
}>()

// Unique clip-path id so three gauges on one page don't collide.
const clipId = useId()

// Pixels (viewBox user units) of horizon travel per degree of pitch.
const PITCH_K = 1.5

const hasValue = computed(() => props.value !== null && Number.isFinite(props.value))
const display = computed(() => (hasValue.value ? `${(props.value as number).toFixed(1)}°` : '--'))

// Bank rotates the horizon the opposite way the chassis tilts.
const rollRotation = computed(() => (hasValue.value ? -(props.value as number) : 0))
// Heading rotates the needle clockwise (north-up rose stays fixed).
const yawRotation = computed(() => (hasValue.value ? (props.value as number) : 0))
// Nose-up drops the horizon; clamp so it never fully leaves the dial.
const pitchOffset = computed(() => {
  if (!hasValue.value) return 0
  return Math.max(-66, Math.min(66, (props.value as number) * PITCH_K))
})

// Bank scale marks around the top of the roll dial (degrees from 12 o'clock).
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

// Pitch ladder rungs (0° is the horizon line itself, so it's omitted here).
const pitchLadder = [-20, -10, 10, 20].map(d => ({
  d,
  y: 50 - d * PITCH_K,
  half: Math.abs(d) === 20 ? 13 : 8,
  abs: Math.abs(d)
}))

// Compass rose: a tick every 30°, longer at the cardinal points.
const yawTicks = Array.from({ length: 12 }, (_, i) => {
  const a = i * 30
  const rad = (a * Math.PI) / 180
  const major = a % 90 === 0
  const inner = major ? 37 : 41
  return {
    a,
    x1: 50 + inner * Math.sin(rad),
    y1: 50 - inner * Math.cos(rad),
    x2: 50 + 46 * Math.sin(rad),
    y2: 50 - 46 * Math.cos(rad),
    major
  }
})
const yawCardinals = [
  { t: 'N', a: 0 },
  { t: 'E', a: 90 },
  { t: 'S', a: 180 },
  { t: 'W', a: 270 }
].map(c => {
  const rad = (c.a * Math.PI) / 180
  return { t: c.t, x: 50 + 29 * Math.sin(rad), y: 50 - 29 * Math.cos(rad) }
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

      <!-- ROLL: sky/ground disc that banks with the roll angle. -->
      <g v-if="mode === 'roll'" :clip-path="`url(#${clipId})`">
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

      <!-- PITCH: sky/ground that climbs/dives, with a pitch ladder. -->
      <g v-else-if="mode === 'pitch'" :clip-path="`url(#${clipId})`">
        <g class="att-move" :transform="`translate(0 ${pitchOffset})`">
          <rect x="0" y="-120" width="100" height="170" fill="#3f6fc4" />
          <rect x="0" y="50" width="100" height="170" fill="#5b7a3a" />
          <line x1="4" y1="50" x2="96" y2="50" stroke="#fff" stroke-width="1.4" />
          <g v-for="m in pitchLadder" :key="m.d">
            <line :x1="50 - m.half" :y1="m.y" :x2="50 + m.half" :y2="m.y" stroke="#e8e8e8" stroke-width="1" />
            <text :x="50 - m.half - 2" :y="m.y + 2" class="ladder-num" text-anchor="end">{{ m.abs }}</text>
            <text :x="50 + m.half + 2" :y="m.y + 2" class="ladder-num" text-anchor="start">{{ m.abs }}</text>
          </g>
        </g>
      </g>

      <!-- YAW: fixed north-up rose with a rotating heading needle. -->
      <g v-else :clip-path="`url(#${clipId})`">
        <line
          v-for="t in yawTicks"
          :key="t.a"
          :x1="t.x1"
          :y1="t.y1"
          :x2="t.x2"
          :y2="t.y2"
          :stroke="t.major ? '#f4f4f4' : '#7f8c9a'"
          :stroke-width="t.major ? 1.6 : 1"
        />
        <text v-for="c in yawCardinals" :key="c.t" :x="c.x" :y="c.y + 3" class="yaw-card" text-anchor="middle">
          {{ c.t }}
        </text>
        <g class="att-move" :transform="`rotate(${yawRotation} 50 50)`">
          <polygon points="50,11 46,52 54,52" fill="#fa4d56" />
          <polygon points="50,89 46,52 54,52" fill="#c1c7cd" />
        </g>
        <circle cx="50" cy="50" r="3.5" fill="#21272a" stroke="#f4f4f4" stroke-width="1" />
      </g>

      <!-- Bezel. -->
      <circle cx="50" cy="50" r="46" fill="none" stroke="#6f6f6f" stroke-width="2.5" />

      <!-- Fixed aircraft reference + top pointer (roll/pitch only). -->
      <g v-if="mode !== 'yaw'">
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
  align-items: center;
  gap: 0.75rem;
}
.att-gauge.stale {
  opacity: 0.5;
}
.att-svg {
  width: 5.25rem;
  height: 5.25rem;
  flex: 0 0 auto;
}
/* Ease the 400ms telemetry steps so the dials glide instead of jumping. */
.att-move {
  transition: transform 0.35s ease-out;
}
.ladder-num {
  font-size: 5.5px;
  fill: #e8e8e8;
  font-family: inherit;
}
.yaw-card {
  font-size: 9px;
  fill: #f4f4f4;
  font-weight: 700;
  font-family: inherit;
}
.att-text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
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
  font-size: 1.5rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
</style>
