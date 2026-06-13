<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api } from './api'
import WebRtcPlayer from './components/WebRtcPlayer.vue'
import { cameraControlSocket, type PtzDirection } from './ws'
import type { ActiveCamera, CameraCode, CameraDevice, Project, RecordingStatus, Report, Session, StreamInfo } from './types'

type Page = 'home' | 'project' | 'console' | 'editor' | 'reports' | 'settings'

const page = ref<Page>('home')
const notice = ref('')
const health = ref<Record<string, unknown>>({})
const cameras = ref<CameraDevice[]>([])
const active = reactive<ActiveCamera>({ device: 'front', channel: 1 })
const stream = ref<StreamInfo | null>(null)
const digitalZoom = ref(1)
const distance = ref(0)
const odometerConnected = ref(false)
let odometerTimer: number | null = null
const segmentMinutes = ref(30)
const recording = ref<RecordingStatus>({ active: false })
const projects = ref<Project[]>([])
const currentProject = ref<Project | null>(null)
const currentSession = ref<Session | null>(null)
const reports = ref<Report[]>([])
const activeReport = ref<Report | null>(null)
const cameraDraft = reactive<Record<CameraCode, Partial<CameraDevice>>>({
  front: {},
  rear: {}
})
const projectForm = reactive({
  name: '',
  fanModel: '',
  fanNo: '',
  bladeModel: '',
  bladeLength: '',
  bladeFactoryNo: '',
  location: ''
})
const markerDraft = reactive({
  defectType: '',
  note: '',
  distanceM: 0
})

const activeCamera = computed(() => cameras.value.find((camera) => camera.code === active.device))
const isPtzChannel = computed(() => active.channel === 1)
const hasProject = computed(() => currentProject.value && currentSession.value)

function show(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 2800)
}

async function loadInitial() {
  health.value = await api.health().catch((error) => ({ error: error.message }))
  cameras.value = await api.listCameras()
  for (const camera of cameras.value) {
    cameraDraft[camera.code] = { ...camera }
  }
  const activeCameraState = await api.getActiveCamera()
  active.device = activeCameraState.device
  active.channel = activeCameraState.channel
  recording.value = await api.recordingStatus()
  projects.value = await api.listProjects()
  await loadStream()
}

async function loadStream() {
  try {
    stream.value = await api.getActiveStream()
  } catch (error) {
    stream.value = null
  }
}

async function selectCamera(device: CameraCode, channel = active.channel) {
  active.device = device
  active.channel = channel
  await api.setActiveCamera({ device, channel })
  digitalZoom.value = 1
  await loadStream()
}

async function selectChannel(channel: number) {
  active.channel = channel
  await api.setActiveCamera({ device: active.device, channel })
  digitalZoom.value = 1
  await loadStream()
}

function ptzStep(direction: PtzDirection) {
  if (!isPtzChannel.value) return
  cameraControlSocket.step(active.device, active.channel, direction)
}

function ptzStart(direction: PtzDirection) {
  if (!isPtzChannel.value) return
  cameraControlSocket.start(active.device, active.channel, direction)
}

function ptzStop() {
  if (!isPtzChannel.value) return
  cameraControlSocket.stop(active.device, active.channel)
}

async function saveCamera(device: CameraCode) {
  const camera = await api.updateCamera(device, cameraDraft[device])
  const index = cameras.value.findIndex((item) => item.code === device)
  if (index >= 0) cameras.value[index] = camera
  show(`${camera.name}配置已保存`)
  await loadStream()
}

async function probeCamera(device: CameraCode) {
  await api.probeCamera(device)
  show('ONVIF 连接成功')
  cameras.value = await api.listCameras()
}

async function createProject() {
  if (!projectForm.name.trim()) {
    show('请填写项目名称')
    return
  }
  currentProject.value = await api.createProject(projectForm)
  currentSession.value = await api.createSession({
    projectId: currentProject.value.id,
    reportTitle: `${currentProject.value.name} 巡检报告`,
    reportLocation: currentProject.value.location
  })
  page.value = 'console'
  show('项目已创建')
}

async function takeSnapshot() {
  const asset = await api.snapshot({
    projectId: currentProject.value?.id,
    sessionId: currentSession.value?.id,
    device: active.device,
    channel: active.channel,
    distanceM: distance.value
  })
  markerDraft.distanceM = distance.value
  page.value = 'editor'
  show(`拍照已保存 #${asset.id}`)
}

async function toggleRecording() {
  if (recording.value.active) {
    recording.value = await api.stopRecording()
    await loadStream()
    show('录像已停止')
    return
  }
  recording.value = await api.startRecording({
    projectId: currentProject.value?.id,
    sessionId: currentSession.value?.id,
    device: active.device,
    channel: active.channel,
    distanceM: distance.value,
    projectName: currentProject.value?.name || '',
    projectLocation: currentProject.value?.location || '',
    segmentMinutes: segmentMinutes.value
  })
  window.setTimeout(loadStream, 800)
  show('录像已开始')
}

async function toggleReport() {
  if (activeReport.value) {
    activeReport.value = await api.stopReport(activeReport.value.id)
    show('报告记录已停止')
    return
  }
  if (!currentProject.value) {
    show('请先新建项目')
    return
  }
  activeReport.value = await api.startReport({
    projectId: currentProject.value.id,
    sessionId: currentSession.value?.id,
    title: `${currentProject.value.name} 巡检报告`,
    location: currentProject.value.location
  })
  show('报告记录已开启')
}

async function loadReports() {
  reports.value = await api.listReports()
  page.value = 'reports'
}

async function exportPdf(report: Report) {
  await api.exportPdf(report.id)
  reports.value = await api.listReports()
  show('PDF 已导出')
}

function openEditor() {
  markerDraft.distanceM = distance.value
  page.value = 'editor'
}

onMounted(() => {
  cameraControlSocket.connect()
  loadInitial().catch((error) => show(error.message))
  // Poll the cart odometer so the OSD overlay distance matches the recording.
  odometerTimer = window.setInterval(async () => {
    try {
      const data = await api.odometer()
      odometerConnected.value = data.connected
      if (data.mileageM !== null) distance.value = data.mileageM
    } catch {
      odometerConnected.value = false
    }
  }, 250)
})

onUnmounted(() => {
  if (odometerTimer !== null) window.clearInterval(odometerTimer)
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">
        <strong>PipeSight</strong>
        <span>风电叶片内腔巡检</span>
      </div>
      <nav>
        <button :class="{ active: page === 'home' }" @click="page = 'home'">首页</button>
        <button :class="{ active: page === 'project' }" @click="page = 'project'">新建项目</button>
        <button :class="{ active: page === 'console' }" @click="page = 'console'">控制</button>
        <button :class="{ active: page === 'reports' }" @click="loadReports">报告</button>
        <button :class="{ active: page === 'settings' }" @click="page = 'settings'">设置</button>
      </nav>
    </header>

    <main>
      <section v-if="page === 'home'" class="home-page">
        <div class="home-actions">
          <button @click="page = 'project'">启动巡检</button>
          <button @click="loadReports">报告中心</button>
          <button @click="page = 'settings'">系统设置</button>
        </div>
        <div class="status-panel">
          <h2>设备状态</h2>
          <div v-for="camera in cameras" :key="camera.code" class="status-row">
            <span>{{ camera.name }}</span>
            <strong>{{ camera.ip || '未配置' }}</strong>
            <em :class="camera.status">{{ camera.status }}</em>
          </div>
          <div class="status-row">
            <span>FFmpeg</span>
            <strong>{{ health.ffmpeg ? '可用' : '未检测到' }}</strong>
          </div>
          <div class="status-row">
            <span>录像</span>
            <strong>{{ recording.active ? '进行中' : '空闲' }}</strong>
          </div>
        </div>
      </section>

      <section v-else-if="page === 'project'" class="form-page">
        <h1>风电机组叶片信息收集表</h1>
        <div class="project-form">
          <label><span>项目名称</span><input v-model="projectForm.name" /></label>
          <label><span>风机机型</span><input v-model="projectForm.fanModel" /></label>
          <label><span>风机编号</span><input v-model="projectForm.fanNo" /></label>
          <label><span>叶片型号</span><input v-model="projectForm.bladeModel" /></label>
          <label><span>叶片长度</span><input v-model="projectForm.bladeLength" /></label>
          <label><span>叶片出厂编号</span><input v-model="projectForm.bladeFactoryNo" /></label>
          <label><span>地点</span><input v-model="projectForm.location" /></label>
        </div>
        <button class="primary-action" @click="createProject">进入控制页</button>
      </section>

      <section v-else-if="page === 'console'" class="console-page">
        <div class="video-area">
          <WebRtcPlayer
            v-if="stream"
            :src="stream.whepUrl"
            v-model:digital-zoom="digitalZoom"
          />
          <div v-else class="video-placeholder">请在系统设置中配置相机，并确认 MediaMTX/WebRTC 可用</div>
          <div class="osd">
            <div>时间：{{ new Date().toLocaleString() }}</div>
            <div>距离：{{ distance.toFixed(2) }}m</div>
            <div>项目名称：{{ currentProject?.name || '未创建项目' }}</div>
            <div>地点：{{ currentProject?.location || '-' }}</div>
          </div>
          <div class="recording-badge" v-if="recording.active">REC</div>
        </div>
        <aside class="control-panel">
          <div class="control-row">
            <button @click="page = 'home'">返回</button>
            <button :class="{ danger: activeReport }" @click="toggleReport">{{ activeReport ? '停止报告' : '开启报告' }}</button>
          </div>
          <div class="segmented">
            <button :class="{ active: active.device === 'front' }" @click="selectCamera('front')">前摄</button>
            <button :class="{ active: active.device === 'rear' }" @click="selectCamera('rear')">后摄</button>
          </div>
          <div class="segmented">
            <button :class="{ active: active.channel === 1 }" @click="selectChannel(1)">云台</button>
            <button :class="{ active: active.channel === 2 }" @click="selectChannel(2)">固定</button>
          </div>
          <label class="distance-input">
            <span>里程 m</span>
            <input :value="distance.toFixed(2)" type="text" readonly :title="odometerConnected ? '来自小车里程计' : '里程计未连接'" />
          </label>
          <div v-if="!odometerConnected" class="odometer-warn">里程计未连接</div>
          <label class="distance-input">
            <span>分段(分钟)</span>
            <input v-model.number="segmentMinutes" type="number" min="1" step="1" :disabled="recording.active" />
          </label>
          <div class="zoom-indicator">
            <span>数字变焦 {{ digitalZoom.toFixed(1) }}x</span>
            <small>双指捏合缩放，单指拖动平移</small>
          </div>
          <div class="control-row">
            <button @click="takeSnapshot">拍照</button>
            <button :class="{ danger: recording.active }" @click="toggleRecording">
              {{ recording.active ? '停止录像' : '开始录像' }}
            </button>
          </div>
          <div class="ptz-block" :class="{ disabled: !isPtzChannel }">
            <span>云台控制</span>
            <div class="ptz-grid">
              <button class="up" @click="ptzStep('up')">▲</button>
              <button class="left" @click="ptzStep('left')">◀</button>
              <button class="right" @click="ptzStep('right')">▶</button>
              <button class="down" @click="ptzStep('down')">▼</button>
            </div>
          </div>
          <button @click="openEditor">进入标记编辑</button>
        </aside>
      </section>

      <section v-else-if="page === 'editor'" class="editor-page">
        <div class="annotation-surface">
          <div class="editor-placeholder">图片标记画布</div>
        </div>
        <div class="editor-tools">
          <button>选择</button>
          <button>画笔</button>
          <button>标记框</button>
          <button>文字</button>
          <button>撤销</button>
          <button>清空</button>
          <label><span>距离 m</span><input v-model.number="markerDraft.distanceM" type="number" step="0.01" /></label>
          <label><span>缺陷类型</span><input v-model="markerDraft.defectType" /></label>
          <label><span>备注</span><input v-model="markerDraft.note" /></label>
          <button class="primary-action" @click="page = 'console'">保存并返回</button>
        </div>
      </section>

      <section v-else-if="page === 'reports'" class="reports-page">
        <h1>报告中心</h1>
        <div class="report-list">
          <article v-for="report in reports" :key="report.id" class="report-item">
            <div>
              <h2>{{ report.title || `巡检报告 #${report.id}` }}</h2>
              <p>地点：{{ report.location || '-' }} / 状态：{{ report.status }}</p>
              <p>时间：{{ new Date(report.startedAt).toLocaleString() }}</p>
            </div>
            <button @click="exportPdf(report)">导出 PDF</button>
          </article>
        </div>
      </section>

      <section v-else-if="page === 'settings'" class="settings-page">
        <h1>系统设置</h1>
        <div class="settings-grid">
          <article v-for="camera in cameras" :key="camera.code" class="settings-card">
            <h2>{{ camera.name }}</h2>
            <label><span>IP</span><input v-model="cameraDraft[camera.code].ip" /></label>
            <label><span>用户名</span><input v-model="cameraDraft[camera.code].username" /></label>
            <label><span>密码</span><input v-model="cameraDraft[camera.code].password" type="password" /></label>
            <label><span>RTSP 端口</span><input v-model.number="cameraDraft[camera.code].rtspPort" type="number" /></label>
            <div class="control-row">
              <button @click="saveCamera(camera.code)">保存</button>
              <button @click="probeCamera(camera.code)">ONVIF 测试</button>
            </div>
          </article>
        </div>
      </section>
    </main>

    <div v-if="notice" class="toast">{{ notice }}</div>
  </div>
</template>
