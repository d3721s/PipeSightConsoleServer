<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvTile, CvButton, CvTag, CvModal } from '@carbon/vue'
import { View24, DocumentPdf24, Report24, DocumentExport24, TrashCan24 } from '@carbon/icons-vue'
import { api } from '../api'
import { notify } from '../stores/session'
import type { Report } from '../types'

const router = useRouter()
const reports = ref<Report[]>([])
const loading = ref(false)

// Delete-confirmation modal state.
const confirmVisible = ref(false)
const pendingDelete = ref<Report | null>(null)
const deleting = ref(false)

async function reload() {
  loading.value = true
  try {
    reports.value = await api.listReports()
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    loading.value = false
  }
}

onMounted(reload)
onActivated(reload)

function statusKind(status: string) {
  if (status === 'exported') return 'green'
  if (status === 'recording' || status === 'active') return 'blue'
  return 'gray'
}

async function exportPdf(report: Report) {
  try {
    await api.exportPdf(report.id)
    await reload()
    notify('PDF 已导出', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

function downloadPdf(id: number) {
  window.open(api.reportPdfUrl(id), '_blank')
}

function askDelete(report: Report) {
  pendingDelete.value = report
  confirmVisible.value = true
}

async function confirmDelete() {
  const report = pendingDelete.value
  if (!report || deleting.value) return
  deleting.value = true
  try {
    await api.deleteReport(report.id)
    confirmVisible.value = false
    pendingDelete.value = null
    await reload()
    notify('报告已删除', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="page reports-page">
    <header class="page-head">
      <h1>报告中心</h1>
      <p class="page-sub">查看巡检报告记录，导出与下载 PDF</p>
    </header>

    <p v-if="!loading && reports.length === 0" class="empty">暂无报告记录</p>

    <div class="report-list">
      <cv-tile v-for="report in reports" :key="report.id" class="report-card">
        <div class="report-card-head">
          <div class="report-card-title">
            <report24 class="report-icon" />
            <div>
              <h3>{{ report.title || `巡检报告 #${report.id}` }}</h3>
              <p class="report-meta">
                地点：{{ report.location || '-' }} ·
                {{ new Date(report.startedAt).toLocaleString() }}
              </p>
            </div>
          </div>
          <cv-tag :kind="statusKind(report.status)" :label="report.status" />
        </div>
        <div class="report-card-actions">
          <cv-button kind="tertiary" :icon="View24" @click="router.push(`/reports/${report.id}`)">查看详情</cv-button>
          <cv-button kind="ghost" :icon="DocumentExport24" @click="exportPdf(report)">重新生成</cv-button>
          <cv-button :icon="DocumentPdf24" @click="downloadPdf(report.id)">下载 PDF</cv-button>
          <cv-button kind="danger--ghost" :icon="TrashCan24" @click="askDelete(report)">删除</cv-button>
        </div>
      </cv-tile>
    </div>

    <cv-modal
      kind="danger"
      :visible="confirmVisible"
      :primary-button-disabled="deleting"
      @update:visible="confirmVisible = $event"
      @primary-click="confirmDelete"
      @secondary-click="confirmVisible = false"
    >
      <template #title>删除报告</template>
      <template #content>
        <p>
          确定删除报告
          「{{ pendingDelete?.title || `巡检报告 #${pendingDelete?.id}` }}」吗？
          此操作会同时删除已生成的 PDF，且不可恢复。
        </p>
      </template>
      <template #secondary-button>取消</template>
      <template #primary-button>删除</template>
    </cv-modal>
  </div>
</template>

<style scoped>
.reports-page {
  max-width: 90rem;
  margin: 0 auto;
}
.report-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.report-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.report-card-title {
  display: flex;
  gap: 0.75rem;
}
.report-icon {
  color: #0f62fe;
  flex-shrink: 0;
}
.report-card-title h3 {
  margin: 0;
  font-size: 1.0625rem;
}
.report-meta {
  margin: 0.25rem 0 0;
  color: #6f6f6f;
  font-size: 0.8125rem;
}
.report-card-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}
/* Full-width buttons so the label sits hard-left and the icon hard-right
   (Carbon's space-between layout needs width to spread them), matching the
   console 采集 buttons. */
.report-card-actions :deep(.bx--btn) {
  flex: 1;
}
.empty {
  color: #6f6f6f;
  text-align: center;
  padding: 3rem 0;
}
</style>
