<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import {
  CvGrid,
  CvRow,
  CvColumn,
  CvTile,
  CvForm,
  CvFormGroup,
  CvTextInput,
  CvNumberInput,
  CvButton,
  CvTag,
  CvInlineNotification,
  CvStructuredList,
  CvStructuredListItem,
  CvStructuredListData
} from '@carbon/vue'
import { Save24, Connect24, Renew24 } from '@carbon/icons-vue'
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

function statusKind(status: string) {
  if (status === 'online') return 'green'
  if (status === 'error') return 'red'
  return 'gray'
}

// --- Storage path -----------------------------------------------------------
const INTERNAL = '__internal__'
const storage = ref<StorageOptions | null>(null)
const storageManualPath = ref('')
const storageBusy = ref(false)

function formatBytes(bytes: number | null): string {
  if (bytes === null) return '—'
  const gb = bytes / 1024 ** 3
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`
}

// Which structured-list row is selected, derived from the active path.
const selectedStorage = computed(() => {
  if (!storage.value) return INTERNAL
  return storage.value.currentPath === storage.value.internal.path
    ? INTERNAL
    : storage.value.currentPath
})

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

// Selecting a structured-list row applies that storage target.
function onStorageSelect(value: string) {
  if (storageBusy.value || !storage.value) return
  if (value === INTERNAL) {
    if (selectedStorage.value !== INTERNAL) applyStorage(null)
    return
  }
  const drive = storage.value.removable.find((d) => d.path === value)
  if (drive && !drive.writable) {
    notify('该存储为只读，无法写入', 'warning')
    return
  }
  if (selectedStorage.value !== value) applyStorage(value)
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

    <cv-grid class="settings-grid" :full-width="true">
      <!-- Camera config cards, two-up on wide screens -->
      <cv-row>
        <cv-column
          v-for="camera in cameras"
          :key="camera.code"
          :sm="4"
          :md="4"
          :lg="8"
          class="settings-col"
        >
          <cv-tile class="settings-card">
            <div class="card-head">
              <h3>{{ camera.name }}</h3>
              <cv-tag :kind="statusKind(camera.status)" :label="camera.status || '未知'" />
            </div>
            <cv-form @submit.prevent>
              <cv-form-group>
                <template #label>连接参数</template>
                <template #content>
                  <cv-text-input v-model="cameraDraft[camera.code].ip" label="IP 地址" placeholder="192.168.x.x" />
                  <cv-text-input v-model="cameraDraft[camera.code].username" label="用户名" />
                  <cv-text-input v-model="cameraDraft[camera.code].password" label="密码" type="password" password-visible />
                  <cv-number-input v-model="cameraDraft[camera.code].rtspPort" label="RTSP 端口" :min="1" :max="65535" />
                </template>
              </cv-form-group>
              <div class="form-actions">
                <cv-button kind="tertiary" :icon="Connect24" @click="probeCamera(camera.code)">ONVIF 测试</cv-button>
                <cv-button :icon="Save24" @click="saveCamera(camera.code)">保存配置</cv-button>
              </div>
            </cv-form>
          </cv-tile>
        </cv-column>
      </cv-row>

      <!-- Storage path, full width -->
      <cv-row>
        <cv-column :sm="4" :md="8" :lg="16" class="settings-col">
          <cv-tile class="settings-card">
            <h3>存储路径</h3>
            <cv-inline-notification
              v-if="storage"
              kind="info"
              :title="storage.usingDefault ? '当前使用内部存储' : '当前使用外部存储'"
              :sub-title="`${storage.currentPath} · 切换后需重启后端生效，旧文件不迁移`"
              :low-contrast="true"
              hide-close-button
            />

            <cv-structured-list
              v-if="storage"
              selectable
              condensed
              class="storage-list"
              @change="onStorageSelect"
            >
              <template #items>
                <cv-structured-list-item :model-value="selectedStorage" :value="INTERNAL">
                  <cv-structured-list-data>内部存储</cv-structured-list-data>
                  <cv-structured-list-data class="path-cell">{{ storage.internal.path }}</cv-structured-list-data>
                  <cv-structured-list-data class="free-cell">剩余 {{ formatBytes(storage.internal.freeBytes) }}</cv-structured-list-data>
                </cv-structured-list-item>

                <cv-structured-list-item
                  v-for="drive in storage.removable"
                  :key="drive.path"
                  :model-value="selectedStorage"
                  :value="drive.path"
                >
                  <cv-structured-list-data>
                    {{ drive.label }}
                    <cv-tag v-if="!drive.writable" kind="red" label="只读" />
                  </cv-structured-list-data>
                  <cv-structured-list-data class="path-cell">{{ drive.path }}</cv-structured-list-data>
                  <cv-structured-list-data class="free-cell">剩余 {{ formatBytes(drive.freeBytes) }}</cv-structured-list-data>
                </cv-structured-list-item>
              </template>
            </cv-structured-list>

            <p v-if="storage && storage.removable.length === 0" class="storage-empty">
              未检测到外部存储（U盘）
            </p>

            <cv-form-group>
              <template #label>手动指定路径</template>
              <template #content>
                <div class="manual-row">
                  <cv-text-input
                    v-model="storageManualPath"
                    label=""
                    hide-label
                    placeholder="/mnt/usb"
                    :disabled="storageBusy"
                    class="manual-input"
                  />
                  <cv-button
                    kind="tertiary"
                    :icon="Save24"
                    :disabled="storageBusy || !storageManualPath.trim()"
                    @click="applyStorage(storageManualPath.trim())"
                  >应用路径</cv-button>
                </div>
              </template>
            </cv-form-group>

            <div class="form-actions">
              <cv-button kind="ghost" :icon="Renew24" :disabled="storageBusy" @click="loadStorage">刷新</cv-button>
            </div>
          </cv-tile>
        </cv-column>
      </cv-row>

      <!-- Recording segment, full width -->
      <cv-row>
        <cv-column :sm="4" :md="8" :lg="16" class="settings-col">
          <cv-tile class="settings-card">
            <h3>录像设置</h3>
            <cv-form @submit.prevent>
              <cv-number-input
                v-model="segmentMinutes"
                label="分段时长（分钟）"
                :min="1"
                :max="120"
                :step="1"
                helper-text="每段录像达到该时长后自动切分为新文件。范围 1–120 分钟。"
              />
              <div class="form-actions">
                <cv-button :icon="Save24" @click="saveRecordingSettings">保存</cv-button>
              </div>
            </cv-form>
          </cv-tile>
        </cv-column>
      </cv-row>
    </cv-grid>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 66rem;
  margin: 0 auto;
}
/* Let Carbon's grid own horizontal rhythm; only add vertical gaps between rows. */
.settings-col {
  margin-bottom: 1.5rem;
}
.settings-card {
  height: 100%;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.settings-card h3 {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 600;
}
.card-head h3 {
  margin: 0;
}
/* Carbon form fields already carry vertical margin; the action row gets a
   clear separation and Carbon's right-aligned button convention. */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1px; /* Carbon button-set seam */
  margin-top: 1.5rem;
}
.storage-list {
  margin: 1rem 0;
}
.path-cell {
  color: #525252;
  font-size: 0.8125rem;
  font-family: 'IBM Plex Mono', monospace;
  word-break: break-all;
}
.free-cell {
  color: #525252;
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.storage-empty {
  color: #6f6f6f;
  font-size: 0.875rem;
  padding: 0.5rem 0 1rem;
}
.manual-row {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
}
.manual-input {
  flex: 1;
}
</style>
