<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvTile, CvButton, CvTag } from '@carbon/vue'
import { View24, DocumentPdf24, Report24, DocumentExport24 } from '@carbon/icons-vue'
import { api } from '../api'
import { notify } from '../stores/session'
import type { Report } from '../types'

const router = useRouter()
const reports = ref<Report[]>([])
const loading = ref(false)

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
        </div>
      </cv-tile>
    </div>
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
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}
.empty {
  color: #6f6f6f;
  text-align: center;
  padding: 3rem 0;
}
</style>
