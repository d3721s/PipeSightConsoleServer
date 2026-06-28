import { ref } from 'vue'
import { api } from '../api'
import { cameraControlSocket } from '../ws'

// Cart odometer distance (metres), still used for saved media metadata and
// annotation defaults. OSD display uses the left/right chassis wheel mileage.

export const distance = ref(0)
export const odometerConnected = ref(false)

// --- Mobile-chassis telemetry (Modbus chassis + IMU light/attitude) ---------
export const leftWheelM = ref<number | null>(null)
export const rightWheelM = ref<number | null>(null)
export const batteryLevel = ref<number | null>(null)
export const faultCode = ref<string | null>(null)
export const chassisId = ref<string | null>(null)
export const chassisConnected = ref(false)
export const chassisLight = ref<number | null>(null) // 1 off / 2 low / 3 high
export const lightPwmPeriod = ref<number | null>(null)
export const lightD1Pulse = ref<number | null>(null)
export const lightD3Pulse = ref<number | null>(null)
// IMU Euler angles (deg) from ATK-MS901M.
export const eulerRoll = ref<number | null>(null)
export const eulerPitch = ref<number | null>(null)
export const eulerYaw = ref<number | null>(null)
export const chassisControlEnabled = ref(true)
export const CHASSIS_MAX_SPEED_MIN = 100
export const CHASSIS_MAX_SPEED_MAX = 800
export const CHASSIS_MAX_SPEED_STEP = 100

const CHASSIS_MAX_SPEED_STORAGE_KEY = 'pipesight.chassisMaxSpeed'

export function clampChassisMaxSpeed(value: string | number) {
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return CHASSIS_MAX_SPEED_MAX
  return Math.max(CHASSIS_MAX_SPEED_MIN, Math.min(CHASSIS_MAX_SPEED_MAX, n))
}

function readStoredChassisMaxSpeed() {
  if (typeof window === 'undefined') return CHASSIS_MAX_SPEED_MAX
  return clampChassisMaxSpeed(window.localStorage.getItem(CHASSIS_MAX_SPEED_STORAGE_KEY) ?? CHASSIS_MAX_SPEED_MAX)
}

export const chassisMaxSpeed = ref(readStoredChassisMaxSpeed())

// Telemetry is polled with a recursive setTimeout (not setInterval) so a slow
// response can never stack another request before the previous one settles. Each
// request is also bounded by a timeout, so a hung connection can't permanently
// freeze the OSD updates. Polling runs app-wide and is never paused (OSD needs it).
const POLL_INTERVAL_MS = 500
const POLL_TIMEOUT_MS = 4000

let odometerPolling = false
let chassisPolling = false
let odometerTimer: number | null = null
let chassisTimer: number | null = null

async function withTimeout<T>(fn: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController()
  const handle = window.setTimeout(() => controller.abort(), POLL_TIMEOUT_MS)
  try {
    return await fn(controller.signal)
  } finally {
    window.clearTimeout(handle)
  }
}

export function setChassisMaxSpeed(value: string | number) {
  chassisMaxSpeed.value = clampChassisMaxSpeed(value)
  try {
    window.localStorage.setItem(CHASSIS_MAX_SPEED_STORAGE_KEY, String(chassisMaxSpeed.value))
  } catch {
    // Ignore storage failures; the runtime value still applies.
  }
}

function clampChassisCommand(value: number) {
  const n = Math.round(Number(value))
  if (!Number.isFinite(n)) return 0
  return Math.max(-chassisMaxSpeed.value, Math.min(chassisMaxSpeed.value, n))
}

export function setChassisControlEnabled(enabled: boolean) {
  if (chassisControlEnabled.value === enabled) return
  chassisControlEnabled.value = enabled
  cameraControlSocket.chassisControlEnabled(enabled)
}

export function sendChassisMove(x: number, y: number) {
  if (!chassisControlEnabled.value) return
  cameraControlSocket.chassisMove(clampChassisCommand(x), clampChassisCommand(y))
}

async function pollOdometer() {
  try {
    const data = await withTimeout(api.odometer)
    odometerConnected.value = data.connected
    if (data.mileageM !== null) distance.value = data.mileageM
  } catch {
    // keep last known distance
  } finally {
    if (odometerPolling) odometerTimer = window.setTimeout(pollOdometer, POLL_INTERVAL_MS)
  }
}

async function pollChassis() {
  try {
    const t = await withTimeout(api.chassisTelemetry)
    chassisConnected.value = t.connected
    // Chassis mileage is reported in metres after backend pulse conversion.
    leftWheelM.value = t.leftMileage
    rightWheelM.value = t.rightMileage
    batteryLevel.value = t.battery
    faultCode.value = t.faultCode === null ? null : `0x${t.faultCode.toString(16).padStart(2, '0')}`
    chassisLight.value = t.light
    lightPwmPeriod.value = t.lightPwm?.periodUs ?? null
    lightD1Pulse.value = t.lightPwm?.d1PulseUs ?? null
    lightD3Pulse.value = t.lightPwm?.d3PulseUs ?? null
    eulerRoll.value = t.roll
    eulerPitch.value = t.pitch
    eulerYaw.value = t.yaw
  } catch {
    chassisConnected.value = false
    batteryLevel.value = null
    faultCode.value = null
    lightPwmPeriod.value = null
    lightD1Pulse.value = null
    lightD3Pulse.value = null
    eulerRoll.value = null
    eulerPitch.value = null
    eulerYaw.value = null
  } finally {
    if (chassisPolling) chassisTimer = window.setTimeout(pollChassis, POLL_INTERVAL_MS)
  }
}

export function startOdometerPolling() {
  if (!odometerPolling) {
    odometerPolling = true
    void pollOdometer()
  }
  if (!chassisPolling) {
    chassisPolling = true
    void pollChassis()
  }
}

export function stopOdometerPolling() {
  odometerPolling = false
  chassisPolling = false
  if (odometerTimer !== null) {
    window.clearTimeout(odometerTimer)
    odometerTimer = null
  }
  if (chassisTimer !== null) {
    window.clearTimeout(chassisTimer)
    chassisTimer = null
  }
}
