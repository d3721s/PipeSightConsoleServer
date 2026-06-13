import { ref } from 'vue'
import { api } from '../api'
import type { Project, Report, Session } from '../types'

// Global, cross-page session state (formerly local refs in App.vue). A single
// module-level instance shared by every page.

export const currentProject = ref<Project | null>(null)
export const currentSession = ref<Session | null>(null)
export const activeReport = ref<Report | null>(null)

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
  if (activeReport.value) {
    activeReport.value = await api.stopReport(activeReport.value.id)
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
}
