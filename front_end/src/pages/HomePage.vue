<script setup lang="ts">
import { useRouter } from 'vue-router'
import { CvTile, CvButton } from '@carbon/vue'
import { Catalog24, Report24, SettingsAdjust24, Play24, ChevronRight16 } from '@carbon/icons-vue'

const router = useRouter()
</script>

<template>
  <div class="page home-page">
    <header class="page-head">
      <h1>风电机组叶片内腔巡检机器人</h1>
      <p class="page-sub"></p>
    </header>

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

    <div class="start-row">
      <cv-button class="start-btn" size="lg" :icon="Play24" @click="router.push('/project')">
        启动巡检
      </cv-button>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 100%;
  margin: 0 auto;
}
.home-tiles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
}
.action-tile {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  min-height: 9rem;
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
  width: 2.75rem;
  height: 2.75rem;
}
.action-tile-body {
  flex: 1;
}
.action-tile-body h3 {
  margin: 0 0 0.375rem;
  font-size: 1.375rem;
}
.action-tile-body p {
  margin: 0;
  color: #525252;
  font-size: 1rem;
}
.action-tile-go {
  color: #6f6f6f;
  width: 1.25rem;
  height: 1.25rem;
}
.start-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 2rem;
}
.start-btn {
  min-width: 16rem;
}
</style>
