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

export interface ChassisTelemetry {
  connected: boolean
  leftSpeed: number | null
  rightSpeed: number | null
  leftMileage: number | null
  rightMileage: number | null
  light: number | null   // IMU D1/D3 PWM: 1 off, 2 low, 3 high
  lightPwm?: LightPwm | null
  mode: number | null    // 0 remote, 1 speed, 3 position, 4 joystick
  error: number | null
  roll: number | null
  pitch: number | null
  yaw: number | null
}

export interface LightPwm {
  periodUs: number
  d1PulseUs: number
  d3PulseUs: number
}

export interface StorageTarget {
  path: string
  label: string
  isMount: boolean
  writable: boolean
  totalBytes: number | null
  freeBytes: number | null
}

export interface StorageOptions {
  currentPath: string
  defaultPath: string
  usingDefault: boolean
  internal: StorageTarget
  removable: StorageTarget[]
  restartRequired?: boolean
}

export interface Recording {
  id: number
  projectId: number | null
  sessionId: number | null
  name: string
  capturedAt: string
  videoUrl: string | null
  trackUrl: string | null
  available: boolean
}

export interface TrackSample {
  videoTime: number
  raw: Record<string, unknown>
}

export interface TrackData {
  video: string
  startedAt?: string
  durationS?: number
  samples: TrackSample[]
}

export interface Marker {
  id: number
  projectId: number | null
  sessionId: number | null
  mediaAssetId: number | null
  defectType: string
  defectCode: string
  severity: string
  direction: string
  position: string
  note: string
  distanceM: number
  createdAt: string
}

export interface Photo {
  id: number
  projectId: number | null
  sessionId: number | null
  name: string
  capturedAt: string
  distanceM: number
  imageUrl: string | null
  available: boolean
}

export interface GraphicAnnotation {
  id: number
  mediaAssetId: number | null
  renderedUrl: string | null
  sourceType: string | null
  videoTime: number | null
  defect: Record<string, unknown>
  shapes: unknown[]
  baseSize: { w?: number; h?: number }
  createdAt: string
}

export interface ReportDetailAnnotation {
  id: number
  renderedUrl: string | null
  sourceType: string | null
  videoTime: number | null
  defect: Record<string, unknown>
  createdAt: string
}

export interface ReportDetail {
  report: {
    id: number
    title: string
    location: string
    status: string
    startedAt: string
    exportedAt: string | null
    pdfReady: boolean
    downloadUrl: string
  }
  project: {
    name: string
    fanModel: string
    fanNo: string
    bladeModel: string
    bladeLength: string
    bladeFactoryNo: string
    location: string
  } | null
  annotations: ReportDetailAnnotation[]
}

