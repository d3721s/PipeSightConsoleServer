export type CameraCode = 'front' | 'rear'

export interface CameraDevice {
  id: number
  code: CameraCode
  name: string
  ip: string
  username: string
  password: string
  onvifPort: number
  rtspPort: number
  status: string
}

export interface ActiveCamera {
  device: CameraCode
  channel: number
}

export interface StreamInfo {
  device: CameraCode
  channel: number
  path: string
  rtspUrl: string
  whepUrl: string
  recordingRelay: boolean
}

export interface Project {
  id: number
  name: string
  fanModel: string
  fanNo: string
  bladeModel: string
  bladeLength: string
  bladeFactoryNo: string
  location: string
  createdAt: string
}

export interface Session {
  id: number
  projectId: number
  startedAt: string
  endedAt?: string | null
  status: string
  reportTitle: string
  reportLocation: string
}

export interface Report {
  id: number
  projectId: number
  sessionId?: number | null
  title: string
  location: string
  status: string
  pdfPath: string
  startedAt: string
  endedAt?: string | null
  exportedAt?: string | null
}

export interface RecordingStatus {
  active: boolean
  device?: CameraCode | null
  channel?: number | null
  startedAt?: string | null
  outputPattern?: string | null
  error?: string | null
}

