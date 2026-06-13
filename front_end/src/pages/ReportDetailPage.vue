<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvButton, CvTile } from '@carbon/vue'
import { ChevronLeft24, DocumentPdf24, DocumentExport24 } from '@carbon/icons-vue'
import { api } from '../api'
import { notify } from '../stores/session'
import type { ReportDetail } from '../types'

const props = defineProps<{ id: string }>()
const router = useRouter()
const detail = ref<ReportDetail | null>(null)

const projectFields: { key: keyof NonNullable<ReportDetail['project']>; label: string }[] = [
  { key: 'name', label: '项目名称' },
  { key: 'fanModel', label: '风机机型' },
  { key: 'fanNo', label: '风机编号' },
  { key: 'bladeModel', label: '叶片型号' },
  { key: 'bladeLength', label: '叶片长度' },
  { key: 'bladeFactoryNo', label: '叶片出厂编号' },
  { key: 'location', label: '地点' }
]

async function load() {
  try {
    detail.value = await api.reportDetail(Number(props.id))
  } catch (e) {
    notify((e as Error).message, 'error')
    router.push('/reports')
  }
}

onMounted(load)

async function regenerate() {
  if (!detail.value) return
  try {
    await api.exportPdf(detail.value.report.id)
    await load()
    notify('PDF 已重新生成', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

function downloadPdf() {
  if (detail.value) window.open(api.reportPdfUrl(detail.value.report.id), '_blank')
}
</script>

<template>
  <div v-if="detail" class="page report-detail-page">
    <div class="detail-toolbar">
      <cv-button kind="ghost" size="sm" :icon="ChevronLeft24" @click="router.push('/reports')">返回报告中心</cv-button>
      <div class="detail-toolbar-right">
        <cv-button kind="tertiary" size="sm" :icon="DocumentExport24" @click="regenerate">重新生成 PDF</cv-button>
        <cv-button size="sm" :icon="DocumentPdf24" @click="downloadPdf">下载 PDF</cv-button>
      </div>
    </div>

    <header class="page-head">
      <h1>{{ detail.report.title || `巡检报告 #${detail.report.id}` }}</h1>
      <p class="page-sub">
        检测时间：{{ new Date(detail.report.startedAt).toLocaleString() }} ·
        标记点 {{ detail.annotations.length }} 个
      </p>
    </header>

    <cv-tile v-if="detail.project" class="meta-tile">
      <h3>机组与叶片信息</h3>
      <dl class="meta-grid">
        <div v-for="f in projectFields" :key="f.key" class="meta-item">
          <dt>{{ f.label }}</dt>
          <dd>{{ detail.project[f.key] || '-' }}</dd>
        </div>
      </dl>
    </cv-tile>

    <h2 class="section-title">标记点（{{ detail.annotations.length }}）</h2>
    <p v-if="detail.annotations.length === 0" class="empty">本次巡检暂无标注</p>

    <div class="anno-grid">
      <cv-tile v-for="(a, i) in detail.annotations" :key="a.id" class="anno-card">
        <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-card-img" />
        <div class="anno-card-info">
          <strong>#{{ i + 1 }} {{ (a.defect.type as string) || '—' }} {{ (a.defect.code as string) }}</strong>
          <small>等级：{{ (a.defect.severity as string) || '-' }} · 方向：{{ (a.defect.direction as string) || '-' }}</small>
          <small>位置：{{ (a.defect.position as string) || '-' }} · 里程：{{ (a.defect.distanceM as number)?.toFixed?.(2) ?? '-' }} m</small>
          <small v-if="a.sourceType === 'video' && a.videoTime !== null">来源：视频帧 {{ a.videoTime.toFixed(1) }} s</small>
          <small v-if="a.defect.note" class="anno-note">备注：{{ a.defect.note as string }}</small>
        </div>
      </cv-tile>
    </div>
  </div>
</template>

<style scoped>
.report-detail-page {
  max-width: 68rem;
  margin: 0 auto;
}
.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.detail-toolbar-right {
  display: flex;
  gap: 0.5rem;
}
.meta-tile h3 {
  margin: 0 0 1rem;
  font-size: 1.0625rem;
}
.meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem 1.5rem;
  margin: 0;
}
.meta-item dt {
  color: #6f6f6f;
  font-size: 0.75rem;
}
.meta-item dd {
  margin: 0.125rem 0 0;
  color: #161616;
}
.section-title {
  font-size: 1.25rem;
  margin: 2rem 0 1rem;
}
.anno-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: 1rem;
}
.anno-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.anno-card-img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  background: #000;
  border: 1px solid #e0e0e0;
}
.anno-card-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.anno-card-info small {
  color: #525252;
  font-size: 0.8125rem;
}
.anno-note {
  color: #6f6f6f !important;
}
.empty {
  color: #6f6f6f;
  padding: 1.5rem 0;
}
</style>
