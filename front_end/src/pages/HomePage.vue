<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvTile, CvButton, CvTag } from '@carbon/vue'
import { Catalog24, Report24, SettingsAdjust24, Play24, ChevronRight16 } from '@carbon/icons-vue'
import { api } from '../api'
import { cameras, recording, ensureLoaded } from '../stores/cameras'
import { odometerConnected } from '../stores/odometer'

const router = useRouter()
const health = ref<Record<string, unknown>>({})

const ffmpegOk = computed(() => Boolean(health.value.ffmpeg))

function statusKind(status: string) {
  if (status === 'online' || status === 'ok') return 'green'
  if (status === 'error') return 'red'
  return 'gray'
}

onMounted(async () => {
  await ensureLoaded().catch(() => undefined)
  health.value = await api.health().catch((e) => ({ error: (e as Error).message }))
})
</script>

<template>
  <div class="page home-page">
    <header class="page-head">
      <h1>风电机组叶片内腔巡检机器人</h1>
      <p class="page-sub">XX有限公司</p>
    </header>

    <div class="home-grid">
      <!-- Left: quick-action tiles -->
      <div class="home-tiles">
        <cv-tile class="action-tile" @click="router.push('/annotate')">
          <div class="action-tile-icon"><catalog24 /></div>
          <div class="action-tile-body">
            <h3>历史影像</h3>
            <p>查看拍照、影像记录与标注</p>
          </div>
          <chevron-right16 class="action-tile-go" />
        </cv-tile>

        <cv-tile class="action-tile" @click="router.push('/reports')">
          <div class="action-tile-icon"><report24 /></div>
          <div class="action-tile-body">
            <h3>报告中心</h3>
            <p>查看往期巡检报告与 PDF 导出</p>
          </div>
          <chevron-right16 class="action-tile-go" />
        </cv-tile>

        <cv-tile class="action-tile" @click="router.push('/settings')">
          <div class="action-tile-icon"><settings-adjust24 /></div>
          <div class="action-tile-body">
            <h3>系统设置</h3>
            <p>相机配置、存储路径、录像分段</p>
          </div>
          <chevron-right16 class="action-tile-go" />
        </cv-tile>
      </div>

      <!-- Right: machine info + status -->
      <cv-tile class="info-tile">
        <h3>机器信息</h3>
        <dl class="info-list">
          <div v-for="camera in cameras" :key="camera.code" class="info-row">
            <dt>{{ camera.name }}</dt>
            <dd>
              <span class="info-ip">{{ camera.ip || '未配置' }}</span>
              <cv-tag :kind="statusKind(camera.status)" :label="camera.status || '未知'" />
            </dd>
          </div>
          <div class="info-row">
            <dt>FFmpeg</dt>
            <dd><cv-tag :kind="ffmpegOk ? 'green' : 'red'" :label="ffmpegOk ? '可用' : '未检测到'" /></dd>
          </div>
          <div class="info-row">
            <dt>里程计</dt>
            <dd><cv-tag :kind="odometerConnected ? 'green' : 'gray'" :label="odometerConnected ? '已连接' : '未连接'" /></dd>
          </div>
          <div class="info-row">
            <dt>录像</dt>
            <dd><cv-tag :kind="recording.active ? 'blue' : 'gray'" :label="recording.active ? '进行中' : '空闲'" /></dd>
          </div>
        </dl>

        <cv-button class="start-btn" size="lg" :icon="Play24" @click="router.push('/project')">
          启动巡检
        </cv-button>
      </cv-tile>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 75rem;
  margin: 0 auto;
}
.home-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 1.5rem;
  align-items: start;
}
.home-tiles {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.action-tile {
  display: flex;
  align-items: center;
  gap: 1rem;
  cursor: pointer;
  transition: background 0.15s ease;
}
.action-tile:hover {
  background: #e8e8e8;
}
.action-tile-icon {
  display: flex;
  color: #0f62fe;
}
.action-tile-icon :deep(svg) {
  width: 2rem;
  height: 2rem;
}
.action-tile-body {
  flex: 1;
}
.action-tile-body h3 {
  margin: 0 0 0.25rem;
  font-size: 1.125rem;
}
.action-tile-body p {
  margin: 0;
  color: #525252;
  font-size: 0.875rem;
}
.action-tile-go {
  color: #6f6f6f;
}
.info-tile h3 {
  margin: 0 0 1rem;
  font-size: 1.125rem;
}
.info-list {
  margin: 0 0 1.5rem;
}
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #e0e0e0;
}
.info-row dt {
  color: #525252;
}
.info-row dd {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.info-ip {
  font-variant-numeric: tabular-nums;
  color: #161616;
}
.start-btn {
  width: 100%;
}
</style>
