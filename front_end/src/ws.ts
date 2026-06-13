import type { CameraCode } from './types'

export type PtzDirection = 'up' | 'down' | 'left' | 'right'

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

  private send(message: Record<string, unknown>) {
    const payload = { ...message, ref: crypto.randomUUID() }
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.queue.push(payload)
      this.connect()
      return
    }
    this.ws.send(JSON.stringify(payload))
  }
}

export const cameraControlSocket = new CameraControlSocket()

