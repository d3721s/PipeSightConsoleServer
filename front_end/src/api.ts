import type { ActiveCamera, CameraCode, CameraDevice, Project, RecordingStatus, Report, Session, StreamInfo } from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init
  })
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = await response.json()
      message = body.detail || message
    } catch {
      // Keep HTTP status text.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Record<string, unknown>>('/api/system/health'),

  listCameras: () => request<CameraDevice[]>('/api/cameras'),
  updateCamera: (device: CameraCode, data: Partial<CameraDevice>) =>
    request<CameraDevice>(`/api/cameras/${device}/config`, {
      method: 'PUT',
      body: JSON.stringify({
        ip: data.ip || '',
        username: data.username || 'admin',
        password: data.password || '',
        onvifPort: 80,
        rtspPort: data.rtspPort || 554
      })
    }),
  probeCamera: (device: CameraCode) =>
    request<Record<string, unknown>>(`/api/cameras/${device}/probe-onvif`, { method: 'POST' }),
  getActiveCamera: () => request<ActiveCamera>('/api/cameras/active'),
  setActiveCamera: (payload: ActiveCamera) =>
    request<ActiveCamera>('/api/cameras/active', { method: 'POST', body: JSON.stringify(payload) }),
  getActiveStream: () => request<StreamInfo>('/api/cameras/active/stream'),

  createProject: (data: Record<string, unknown>) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
  listProjects: () => request<Project[]>('/api/projects'),
  createSession: (data: Record<string, unknown>) =>
    request<Session>('/api/sessions', { method: 'POST', body: JSON.stringify(data) }),
  finishSession: (id: number) => request<Session>(`/api/sessions/${id}/finish`, { method: 'POST' }),

  snapshot: (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/snapshots', { method: 'POST', body: JSON.stringify(data) }),
  startRecording: (data: Record<string, unknown>) =>
    request<RecordingStatus>('/api/recordings/start', { method: 'POST', body: JSON.stringify(data) }),
  stopRecording: () => request<RecordingStatus>('/api/recordings/stop', { method: 'POST' }),
  recordingStatus: () => request<RecordingStatus>('/api/recordings/status'),
  odometer: () => request<{ connected: boolean; mileageCm: number | null; mileageM: number | null }>('/api/odometer'),

  startReport: (data: Record<string, unknown>) =>
    request<Report>('/api/reports/start', { method: 'POST', body: JSON.stringify(data) }),
  stopReport: (id: number) => request<Report>(`/api/reports/${id}/stop`, { method: 'POST' }),
  listReports: () => request<Report[]>('/api/reports'),
  exportPdf: (id: number) => request<Record<string, unknown>>(`/api/reports/${id}/export-pdf`, { method: 'POST' })
}

