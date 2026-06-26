<script setup lang="ts">
import { computed, useId } from 'vue'

// A combined primary-flight-display ("姿态仪"): one dial that fuses all three
// Euler angles the way an aircraft PFD does —
//   roll  — the sky/ground disc banks (rotates) and a bank pointer swings
//   pitch — the horizon line + pitch ladder climb/dive (translate)
//   yaw   — the outer compass ring rotates so the current heading is at top
// Numeric readouts for all three sit below the dial.
const props = defineProps<{
  roll: number | null
  pitch: number | null
  yaw: number | null
}>()

// Unique clip-path id so several dials on one page don't collide.
const clipId = useId()

// Pixels (viewBox user units) of horizon travel per degree of pitch.
const PITCH_K = 1.5
// Inner ADI radius (the banking sky/ground disc lives inside this).
const ADI_R = 33

const fin = (v: number | null): v is number => v !== null && Number.isFinite(v)
const fmt = (v: number | null) => (fin(v) ? `${v.toFixed(1)}°` : '--')
const hasAny = computed(() => fin(props.roll) || fin(props.pitch) || fin(props.yaw))

const rollText = computed(() => fmt(props.roll))
const pitchText = computed(() => fmt(props.pitch))
// Heading reads -180–+180 (normalize so e.g. 190 shows as -170.0).
const wrap180 = (deg: number) => ((((deg + 180) % 360) + 360) % 360) - 180
const yawText = computed(() => (fin(props.yaw) ? `${wrap180(props.yaw).toFixed(1)}°` : '--'))

// Bank rotates the horizon the opposite way the chassis tilts.
const rollRotation = computed(() => (fin(props.roll) ? -props.roll : 0))
// Compass ring rotates so the current heading comes up to the top index.
const yawRotation = computed(() => (fin(props.yaw) ? -props.yaw : 0))
// Pitch scrolls the horizon + ladder freely (no clamp) so the current pitch
// always sits at the dial center; the ADI clip hides whatever is off-window.
const pitchOffset = computed(() => (fin(props.pitch) ? props.pitch * PITCH_K : 0))

// Pitch ladder: a signed rung every 10° across the full ±180 range. Only the
// few rungs near the current pitch fall inside the ADI clip, so it scrolls.
const pitchLadder = Array.from({ length: 37 }, (_, i) => (i - 18) * 10)
  .filter(d => d !== 0)
  .map(d => ({
    d,
    y: 50 - d * PITCH_K,
    half: d % 30 === 0 ? 9 : 6,
    label: String(d)
  }))

// Bank scale on the fixed arc just inside the compass ring (0/±30/±60).
const bankTicks = [-60, -30, 0, 30, 60].map(a => {
  const rad = (a * Math.PI) / 180
  const inner = a === 0 ? 36 : 38
  return {
    a,
    x1: 50 + inner * Math.sin(rad),
    y1: 50 - inner * Math.cos(rad),
    x2: 50 + 41 * Math.sin(rad),
    y2: 50 - 41 * Math.cos(rad)
  }
})

// Compass ring: a tick every 10°, longer + numbered every 30° (0–360).
const headingTicks = Array.from({ length: 36 }, (_, i) => {
  const a = i * 10
  const rad = (a * Math.PI) / 180
  const major = a % 30 === 0
  const inner = major ? 43 : 45
  return {
    a,
    x1: 50 + inner * Math.sin(rad),
    y1: 50 - inner * Math.cos(rad),
    x2: 50 + 47.5 * Math.sin(rad),
    y2: 50 - 47.5 * Math.cos(rad),
    major
  }
})
const headingLabels = Array.from({ length: 12 }, (_, i) => {
  const a = i * 30
  const rad = (a * Math.PI) / 180
  // Ring is labeled -180–+180; the bottom point reads 180 (not -180).
  const signed = a === 180 ? 180 : wrap180(a)
  return {
    a,
    x: 50 + 39.5 * Math.sin(rad),
    y: 50 - 39.5 * Math.cos(rad),
    text: String(signed)
  }
})
</script>

<template>
  <div class="pfd" :class="{ stale: !hasAny }">
    <svg class="pfd-svg" viewBox="0 0 100 100" aria-hidden="true">
      <defs>
        <clipPath :id="clipId"><circle cx="50" cy="50" :r="ADI_R" /></clipPath>
      </defs>

      <!-- Outer ring backdrop. -->
      <circle cx="50" cy="50" r="49" fill="#10161d" />

      <!-- Rotating compass ring (heading 0–360, current heading at top). -->
      <g class="pfd-move" :transform="`rotate(${yawRotation} 50 50)`">
        <line
          v-for="t in headingTicks"
          :key="t.a"
          :x1="t.x1"
          :y1="t.y1"
          :x2="t.x2"
          :y2="t.y2"
          :stroke="t.major ? '#f4f4f4' : '#7f8c9a'"
          :stroke-width="t.major ? 1 : 0.6"
        />
        <text
          v-for="l in headingLabels"
          :key="l.a"
          :x="l.x"
          :y="l.y"
          class="ring-num"
          text-anchor="middle"
          dominant-baseline="central"
          :transform="`rotate(${-yawRotation} ${l.x} ${l.y})`"
        >{{ l.text }}</text>
      </g>

      <!-- ADI: banking sky/ground disc with a climbing/diving pitch ladder. -->
      <g :clip-path="`url(#${clipId})`">
        <g class="pfd-move" :transform="`rotate(${rollRotation} 50 50)`">
          <g :transform="`translate(0 ${pitchOffset})`">
            <rect x="-60" y="-400" width="220" height="450" fill="#1ca3e0" />
            <rect x="-60" y="50" width="220" height="450" fill="#9e7c45" />
            <line x1="-60" y1="50" x2="160" y2="50" stroke="#fff" stroke-width="1" />
            <g v-for="m in pitchLadder" :key="m.d">
              <line :x1="50 - m.half" :y1="m.y" :x2="50 + m.half" :y2="m.y" stroke="#ffffff" stroke-width="0.7" />
              <text :x="50 - m.half - 1.5" :y="m.y" class="ladder-num" text-anchor="end" dominant-baseline="central">{{ m.label }}</text>
              <text :x="50 + m.half + 1.5" :y="m.y" class="ladder-num" text-anchor="start" dominant-baseline="central">{{ m.label }}</text>
            </g>
          </g>
        </g>
      </g>
      <circle cx="50" cy="50" :r="ADI_R" fill="none" stroke="#0c1218" stroke-width="1" />

      <!-- Fixed bank scale + rotating bank pointer (between ADI and ring). -->
      <line
        v-for="t in bankTicks"
        :key="t.a"
        :x1="t.x1"
        :y1="t.y1"
        :x2="t.x2"
        :y2="t.y2"
        stroke="#ffffff"
        stroke-width="0.8"
      />
      <!-- Fixed top index. -->
      <polygon points="50,7 47.5,12 52.5,12" fill="#ffffff" />
      <!-- Bank pointer swings with roll. -->
      <g class="pfd-move" :transform="`rotate(${rollRotation} 50 50)`">
        <polygon points="50,12 47.8,16.5 52.2,16.5" fill="#ffffff" />
      </g>

      <!-- Fixed aircraft reference in the center. -->
      <g>
        <line x1="34" y1="50" x2="44" y2="50" stroke="#ffd500" stroke-width="1.8" />
        <line x1="56" y1="50" x2="66" y2="50" stroke="#ffd500" stroke-width="1.8" />
        <circle cx="50" cy="50" r="1.4" fill="#ffd500" />
      </g>

      <!-- Bezel. -->
      <circle cx="50" cy="50" r="49" fill="none" stroke="#6f6f6f" stroke-width="2" />
    </svg>

    <div class="pfd-readouts">
      <div class="ro"><span class="ro-label">横滚 ROLL</span><span class="ro-value">{{ rollText }}</span></div>
      <div class="ro"><span class="ro-label">俯仰 PITCH</span><span class="ro-value">{{ pitchText }}</span></div>
      <div class="ro"><span class="ro-label">航向 YAW</span><span class="ro-value">{{ yawText }}</span></div>
    </div>
  </div>
</template>

<style scoped>
.pfd {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
}
.pfd.stale {
  opacity: 0.5;
}
.pfd-svg {
  width: 11rem;
  height: 11rem;
  flex: 0 0 auto;
}
/* Ease the 400ms telemetry steps so the dial glides instead of jumping. */
.pfd-move {
  transition: transform 0.35s ease-out;
}
.ring-num {
  font-size: 3.6px;
  fill: #f4f4f4;
  font-weight: 600;
  font-family: inherit;
}
.ladder-num {
  font-size: 4px;
  fill: #ffffff;
  font-family: inherit;
}
.pfd-readouts {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.ro {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  min-width: 0;
}
.ro-label {
  color: #8d8d8d;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.ro-value {
  color: #f4f4f4;
  font-size: 1.125rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
</style>
