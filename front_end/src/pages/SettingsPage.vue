<script setup lang="ts">
import { onActivated, onMounted, reactive, ref } from 'vue'
import { CvTile, CvTextInput, CvNumberInput, CvButton, CvTag, CvInlineNotification } from '@carbon/vue'
import { Save24, Connect24, Renew24, Folder24, VolumeFileStorage24, CheckmarkOutline16 } from '@carbon/icons-vue'
import { api } from '../api'
import { cameras, loadCameras } from '../stores/cameras'
import { notify } from '../stores/session'
import type { CameraCode, CameraDevice, StorageOptions } from '../types'

// --- Camera config ----------------------------------------------------------
const cameraDraft = reactive<Record<CameraCode, Partial<CameraDevice>>>({
  front: {},
  rear: {}
})

function syncDraft() {
  for (const c of cameras.value) cameraDraft[c.code] = { ...c }
}

async function saveCamera(code: CameraCode) {
  try {
    const updated = await api.updateCamera(code, cameraDraft[code])
    const i = cameras.value.findIndex((c) => c.code === code)
    if (i >= 0) cameras.value[i] = updated
    notify(`${updated.name}配置已保存`, 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

async function probeCamera(code: CameraCode) {
  try {
    await api.probeCamera(code)
    notify('ONVIF 连接成功', 'success')
    await loadCameras()
    syncDraft()
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

// --- Storage path -----------------------------------------------------------
const storage = ref<StorageOptions | null>(null)
const storageManualPath = ref('')
const storageBusy = ref(false)

function formatBytes(bytes: number | null): string {
  if (bytes === null) return '—'
  const gb = bytes / 1024 ** 3
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`
}

async function loadStorage() {
  try {
    storage.value = await api.getStorage()
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

async function applyStorage(path: string | null) {
  if (storageBusy.value) return
  storageBusy.value = true
  try {
    storage.value = await api.setStorage(path)
    notify('存储路径已保存，请重启后端使其生效', 'warning')
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    storageBusy.value = false
  }
}

// --- Recording segment ------------------------------------------------------
const segmentMinutes = ref(30)

async function loadRecordingSettings() {
  try {
    const data = await api.getRecordingSettings()
    segmentMinutes.value = data.segmentMinutes
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

async function saveRecordingSettings() {
  try {
    const data = await api.setRecordingSettings(segmentMinutes.value)
    segmentMinutes.value = data.segmentMinutes
    notify('录像分段已保存', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

async function loadAll() {
  await loadCameras().catch(() => undefined)
  syncDraft()
  await Promise.all([loadStorage(), loadRecordingSettings()])
}

onMounted(loadAll)
onActivated(loadStorage)
</script>

<template>
  <div class="page settings-page">
    <header class="page-head">
      <h1>系统设置</h1>
      <p class="page-sub">相机配置、存储路径与录像分段</p>
    </header>

    <div class="settings-grid">
      <!-- Camera config cards -->
      <cv-tile v-for="camera in cameras" :key="camera.code" class="settings-card">
        <h3>{{ camera.name }}</h3>
        <div class="card-fields">
          <cv-text-input v-model="cameraDraft[camera.code].ip" label="IP 地址" placeholder="192.168.x.x" />
          <cv-text-input v-model="cameraDraft[camera.code].username" label="用户名" />
          <cv-text-input v-model="cameraDraft[camera.code].password" label="密码" type="password" password-visible />
          <cv-number-input v-model="cameraDraft[camera.code].rtspPort" label="RTSP 端口" :min="1" :max="65535" />
        </div>
        <div class="card-actions">
          <cv-tag :kind="camera.status === 'online' ? 'green' : camera.status === 'error' ? 'red' : 'gray'" :label="camera.status || '未知'" />
          <span class="spacer" />
          <cv-button size="sm" kind="tertiary" :icon="Connect24" @click="probeCamera(camera.code)">ONVIF 测试</cv-button>
          <cv-button size="sm" :icon="Save24" @click="saveCamera(camera.code)">保存</cv-button>
        </div>
      </cv-tile>

      <!-- Storage path -->
      <cv-tile class="settings-card storage-card">
        <h3>存储路径</h3>
        <cv-inline-notification
          v-if="storage"
          kind="info"
          :title="storage.usingDefault ? '当前使用内部存储' : '当前使用外部存储'"
          :sub-title="`${storage.currentPath} · 切换后需重启后端生效，旧文件不迁移`"
          :low-contrast="true"
          hide-close-button
        />

        <div v-if="storage" class="storage-list">
          <button
            class="storage-option"
            :class="{ active: storage.currentPath === storage.internal.path }"
            :disabled="storageBusy"
            @click="applyStorage(null)"
          >
            <folder24 class="storage-icon" />
            <span class="storage-text">
              <strong>内部存储 <checkmark-outline16 v-if="storage.currentPath === storage.internal.path" class="storage-check" /></strong>
              <small>{{ storage.internal.path }}</small>
            </span>
            <span class="storage-free">剩余 {{ formatBytes(storage.internal.freeBytes) }}</span>
          </button>

          <button
            v-for="drive in storage.removable"
            :key="drive.path"
            class="storage-option"
            :class="{ active: storage.currentPath === drive.path }"
            :disabled="storageBusy || !drive.writable"
            @click="applyStorage(drive.path)"
          >
            <volume-file-storage24 class="storage-icon" />
            <span class="storage-text">
              <strong>
                {{ drive.label }}
                <cv-tag v-if="!drive.writable" kind="red" label="只读" />
                <checkmark-outline16 v-if="storage.currentPath === drive.path" class="storage-check" />
              </strong>
              <small>{{ drive.path }}</small>
            </span>
            <span class="storage-free">剩余 {{ formatBytes(drive.freeBytes) }}</span>
          </button>

          <p v-if="storage.removable.length === 0" class="empty">未检测到外部存储（U盘）</p>
        </div>

        <cv-text-input
          v-model="storageManualPath"
          label="手动指定路径"
          placeholder="/mnt/usb"
          :disabled="storageBusy"
        />
        <div class="card-actions">
          <span class="spacer" />
          <cv-button size="sm" kind="ghost" :icon="Renew24" :disabled="storageBusy" @click="loadStorage">刷新</cv-button>
          <cv-button
            size="sm"
            :icon="Save24"
            :disabled="storageBusy || !storageManualPath.trim()"
            @click="applyStorage(storageManualPath.trim())"
          >保存路径</cv-button>
        </div>
      </cv-tile>

      <!-- Recording segment -->
      <cv-tile class="settings-card">
        <h3>录像设置</h3>
        <cv-number-input
          v-model="segmentMinutes"
          label="分段时长（分钟）"
          :min="1"
          :max="120"
          :step="1"
          helper-text="每段录像达到该时长后自动切分为新文件。范围 1–120 分钟。"
        />
        <div class="card-actions">
          <span class="spacer" />
          <cv-button size="sm" :icon="Save24" @click="saveRecordingSettings">保存</cv-button>
        </div>
      </cv-tile>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 64rem;
  margin: 0 auto;
}
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem;
  align-items: start;
}
.settings-card h3 {
  margin: 0 0 1rem;
  font-size: 1.0625rem;
}
.storage-card {
  grid-column: 1 / -1;
}
.card-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem 1rem;
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1rem;
}
.spacer {
  flex: 1;
}
.storage-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1rem 0;
}
.storage-option {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: #ffffff;
  border: 1px solid #e0e0e0;
  border-left: 3px solid transparent;
  color: #161616;
  cursor: pointer;
  text-align: left;
}
.storage-option:hover:not(:disabled) {
  background: #e8e8e8;
}
.storage-option.active {
  border-left-color: #0f62fe;
  background: #e0e0e0;
}
.storage-option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.storage-icon {
  color: #0f62fe;
  flex-shrink: 0;
}
.storage-text {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.storage-text strong {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.storage-text small {
  color: #6f6f6f;
  font-size: 0.75rem;
}
.storage-check {
  color: #24a148;
}
.storage-free {
  color: #525252;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
}
.empty {
  color: #6f6f6f;
  font-size: 0.875rem;
  padding: 0.5rem 0;
}
</style>
