import type { CameraCode } from './types'

export type PtzDirection = 'up' | 'down' | 'left' | 'right'

// crypto.randomUUID() only exists in a secure context (https or localhost).
// Over plain http://<lan-ip> it is undefined, which used to throw inside send()
// and silently swallow every PTZ command. This ref only needs to be unique for
// ack matching, so a counter+timestamp is enough and works in any context.
let refCounter = 0
function nextRef(): string {
  refCounter += 1
  return `ref-${Date.now().toString(36)}-${refCounter}`
}

export class CameraControlSocket {
  private ws: WebSocket | null = null
  private queue: Array<Record<string, unknown>> = []

  connect() {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.ws = new WebSocket(`${protocol}//${location.host}/ws/camera-control`)
    this.ws.onopen = () => {
      const queued = [...this.queue]
      this.queue = []
      queued.forEach((msg) => this.send(msg))
    }
    this.ws.onclose = () => {
      setTimeout(() => this.connect(), 1000)
    }
  }

  step(device: CameraCode, channel: number, direction: PtzDirection) {
    this.send({ type: 'ptz_step', device, channel, direction })
  }

  start(device: CameraCode, channel: number, direction: PtzDirection) {
    this.send({ type: 'ptz_start', device, channel, direction })
  }

  stop(device: CameraCode, channel: number) {
    this.send({ type: 'ptz_stop', device, channel })
  }

  // Chassis joystick: x = horizontal, y = vertical, both -800..800.
  chassisMove(x: number, y: number) {
    this.send({ type: 'chassis_move', x: Math.round(x), y: Math.round(y) })
  }

  private send(message: Record<string, unknown>) {
    const payload = { ...message, ref: nextRef() }
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.queue.push(payload)
      this.connect()
      return
    }
    this.ws.send(JSON.stringify(payload))
  }
}

export const cameraControlSocket = new CameraControlSocket()

