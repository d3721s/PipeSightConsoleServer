import { ref, watch } from 'vue'
import { api } from '../api'
import { recording, recordingBusy } from './cameras'
import type { Project, Report, Session } from '../types'

// Global, cross-page session state (formerly local refs in App.vue). A single
// module-level instance shared by every page.

export const currentProject = ref<Project | null>(null)
export const currentSession = ref<Session | null>(null)
export const activeReport = ref<Report | null>(null)
export const reportToggling = ref(false)

// --- Persistence across page reloads ----------------------------------------
// The refs above live only in memory, so a browser refresh would otherwise drop
// the current project/session and orphan the running report. We persist their
// ids to localStorage and restore them from the backend on startup.
const LS_PROJECT = 'pipesight.currentProjectId'
const LS_SESSION = 'pipesight.currentSessionId'

function storeId(key: string, id: number | null | undefined) {
  try {
    if (id == null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, String(id))
  } catch {
    // Ignore storage failures; runtime state still works for this session.
  }
}

function readId(key: string): number | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  } catch {
    return null
  }
}

watch(currentProject, (p) => storeId(LS_PROJECT, p?.id), { deep: false })
watch(currentSession, (s) => storeId(LS_SESSION, s?.id), { deep: false })

// Re-hydrate session state after a reload: fetch the stored project/session and
// the single running report (authoritative source) from the backend. Stored ids
// that no longer resolve (deleted) are cleared silently.
export async function restoreSession() {
  const projectId = readId(LS_PROJECT)
  if (projectId !== null && currentProject.value === null) {
    try {
      currentProject.value = await api.getProject(projectId)
    } catch {
      storeId(LS_PROJECT, null)
    }
  }
  const sessionId = readId(LS_SESSION)
  if (sessionId !== null && currentSession.value === null) {
    try {
      currentSession.value = await api.getSession(sessionId)
    } catch {
      storeId(LS_SESSION, null)
    }
  }
  // Report state comes from the backend's running report, not a stored id, so it
  // stays correct even across devices and respects the single-running rule.
  if (activeReport.value === null) {
    try {
      activeReport.value = (await api.currentReport()) ?? null
    } catch {
      // Leave null on failure; user can re-toggle.
    }
  }
}

// --- Global toast notification ----------------------------------------------
export interface Notice {
  kind: 'success' | 'error' | 'info' | 'warning'
  text: string
}
export const notice = ref<Notice | null>(null)
let noticeTimer: number | null = null

export function notify(text: string, kind: Notice['kind'] = 'info') {
  notice.value = { kind, text }
  if (noticeTimer !== null) window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => {
    notice.value = null
  }, 3200)
}

export function clearNotice() {
  notice.value = null
  if (noticeTimer !== null) window.clearTimeout(noticeTimer)
}

export const hasActiveSession = () => Boolean(currentProject.value && currentSession.value)

// Create a project + its inspection session in one step (matches the old flow).
export async function createProjectWithSession(form: Record<string, unknown>) {
  const project = await api.createProject(form)
  const session = await api.createSession({
    projectId: project.id,
    reportTitle: `${project.name} 巡检报告`,
    reportLocation: project.location
  })
  currentProject.value = project
  currentSession.value = session
  return { project, session }
}

export async function toggleReport() {
  if (reportToggling.value) return
  reportToggling.value = true
  try {
    if (activeReport.value) {
      await api.stopReport(activeReport.value.id)
      activeReport.value = null
      notify('报告记录已停止', 'info')
      return
    }
    if (!currentProject.value) {
      notify('请先新建项目', 'warning')
      return
    }
    activeReport.value = await api.startReport({
      projectId: currentProject.value.id,
      sessionId: currentSession.value?.id,
      title: `${currentProject.value.name} 巡检报告`,
      location: currentProject.value.location
    })
    notify('报告记录已开启', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    reportToggling.value = false
  }
}

// --- Background status sync --------------------------------------------------
// The report/recording button colors are driven by `activeReport` / `recording`.
// Those are otherwise only updated by the buttons themselves, so they drift when
// the backend changes state on its own (recording auto-segments/finishes) or
// another tab/device toggles them — leaving stale button colors. A slow poll
// keeps both in sync with the backend. ~2s is plenty (states change rarely) and
// is far cheaper than the 500ms telemetry poll. Skips while an action is mid-flight.
const STATUS_SYNC_MS = 2000
const STATUS_SYNC_TIMEOUT_MS = 4000
let statusSyncing = false
let statusTimer: number | null = null

async function withStatusTimeout<T>(fn: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController()
  const handle = window.setTimeout(() => controller.abort(), STATUS_SYNC_TIMEOUT_MS)
  try {
    return await fn(controller.signal)
  } finally {
    window.clearTimeout(handle)
  }
}

async function pollStatus() {
  try {
    if (!reportToggling.value) {
      const r = await withStatusTimeout(() => api.currentReport())
      // Re-check the guard: an action may have started during the await.
      if (!reportToggling.value) activeReport.value = r ?? null
    }
    if (!recordingBusy.value) {
      const rec = await withStatusTimeout(() => api.recordingStatus())
      if (!recordingBusy.value) recording.value = rec
    }
  } catch {
    // Transient failure — keep last known state, try again next tick.
  } finally {
    if (statusSyncing) statusTimer = window.setTimeout(pollStatus, STATUS_SYNC_MS)
  }
}

export function startStatusSync() {
  if (statusSyncing) return
  statusSyncing = true
  void pollStatus()
}

export function stopStatusSync() {
  statusSyncing = false
  if (statusTimer !== null) {
    window.clearTimeout(statusTimer)
    statusTimer = null
  }
}
