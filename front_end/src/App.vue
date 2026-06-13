<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { api } from './api'
import WebRtcPlayer from './components/WebRtcPlayer.vue'
import AnnotationEditor from './components/AnnotationEditor.vue'
import { cameraControlSocket, type PtzDirection } from './ws'
import type { ActiveCamera, CameraCode, CameraDevice, GraphicAnnotation, Photo, Project, Recording, RecordingStatus, Report, Session, StorageOptions, StreamInfo, TrackData } from './types'

type Page = 'home' | 'project' | 'console' | 'editor' | 'annotate' | 'reports' | 'settings'

const page = ref<Page>('home')
const notice = ref('')
const health = ref<Record<string, unknown>>({})
const cameras = ref<CameraDevice[]>([])
const active = reactive<ActiveCamera>({ device: 'front', channel: 1 })
const stream = ref<StreamInfo | null>(null)
const digitalZoom = ref(1)
const distance = ref(0)
let odometerTimer: number | null = null
const segmentMinutes = ref(30)
const storage = ref<StorageOptions | null>(null)
const storageManualPath = ref('')
const storageBusy = ref(false)

// Video annotation page state.
const annotateTab = ref<'image' | 'video'>('image')
const recordings = ref<Recording[]>([])
const activeRecording = ref<Recording | null>(null)
const annotateVideo = ref<HTMLVideoElement | null>(null)
const track = ref<TrackData | null>(null)
const videoCurrentTime = ref(0)

const photos = ref<Photo[]>([])
const activePhoto = ref<Photo | null>(null)
const editorBaseImage = ref<string>('')      // current image/frame being annotated
const editorOpen = ref(false)
const editorSourceType = ref<'photo' | 'video'>('photo')
const editorVideoTime = ref<number | null>(null)
const editorDistance = ref(0)
const graphicAnnotations = ref<GraphicAnnotation[]>([])
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

function formatBytes(bytes: number | null): string {
  if (bytes === null) return '—'
  const gb = bytes / 1024 ** 3
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`
}

async function loadStorage() {
  try {
    storage.value = await api.getStorage()
  } catch (error) {
    show((error as Error).message)
  }
}

async function applyStorage(path: string | null) {
  if (storageBusy.value) return
  storageBusy.value = true
  try {
    storage.value = await api.setStorage(path)
    show('存储路径已保存，请重启后端使其生效')
  } catch (error) {
    show((error as Error).message)
  } finally {
    storageBusy.value = false
  }
}

async function loadRecordingSettings() {
  try {
    const data = await api.getRecordingSettings()
    segmentMinutes.value = data.segmentMinutes
  } catch (error) {
    show((error as Error).message)
  }
}

async function saveRecordingSettings() {
  try {
    const data = await api.setRecordingSettings(segmentMinutes.value)
    segmentMinutes.value = data.segmentMinutes
    show('录像分段已保存')
  } catch (error) {
    show((error as Error).message)
  }
}

async function openAnnotate() {
  page.value = 'annotate'
  activeRecording.value = null
  activePhoto.value = null
  track.value = null
  editorOpen.value = false
  graphicAnnotations.value = []
  try {
    const [recs, pics] = await Promise.all([api.listRecordings(), api.listPhotos()])
    recordings.value = recs
    photos.value = pics
  } catch (error) {
    show((error as Error).message)
  }
}

async function loadGraphicAnnotations(mediaId: number) {
  try {
    graphicAnnotations.value = await api.listGraphicAnnotations(mediaId)
  } catch {
    graphicAnnotations.value = []
  }
}

async function selectRecording(recording: Recording) {
  activeRecording.value = recording
  activePhoto.value = null
  track.value = null
  editorOpen.value = false
  videoCurrentTime.value = 0
  try {
    track.value = await api.recordingTrack(recording.id)
  } catch (error) {
    show((error as Error).message)
  }
  await loadGraphicAnnotations(recording.id)
}

async function selectPhoto(photo: Photo) {
  activePhoto.value = photo
  activeRecording.value = null
  editorOpen.value = false
  await loadGraphicAnnotations(photo.id)
}

// Mileage (m) at the current video position, from the nearest track sample.
const currentMileageM = computed(() => {
  const samples = track.value?.samples
  if (!samples || samples.length === 0) return null
  const t = videoCurrentTime.value
  let best = samples[0]
  let bestDelta = Math.abs(best.videoTime - t)
  for (const sample of samples) {
    const delta = Math.abs(sample.videoTime - t)
    if (delta < bestDelta) {
      best = sample
      bestDelta = delta
    }
  }
  const cm = best.raw?.mileage_cm
  return typeof cm === 'number' ? cm / 100 : null
})

function onAnnotateTimeUpdate() {
  if (annotateVideo.value) videoCurrentTime.value = annotateVideo.value.currentTime
}

// Open the graphic editor for the selected photo.
function annotatePhoto() {
  if (!activePhoto.value?.imageUrl) return
  editorSourceType.value = 'photo'
  editorBaseImage.value = activePhoto.value.imageUrl
  editorVideoTime.value = null
  editorDistance.value = activePhoto.value.distanceM ?? 0
  editorOpen.value = true
}

// Capture the current video frame and open the editor on it.
function annotateFrame() {
  const video = annotateVideo.value
  if (!video) return
  const c = document.createElement('canvas')
  c.width = video.videoWidth
  c.height = video.videoHeight
  const ctx = c.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, c.width, c.height)
  editorSourceType.value = 'video'
  editorBaseImage.value = c.toDataURL('image/png')
  editorVideoTime.value = video.currentTime
  editorDistance.value = currentMileageM.value ?? 0
  editorOpen.value = true
}

async function saveGraphicAnnotation(payload: {
  shapes: unknown[]
  baseSize: { w: number; h: number }
  renderedPng: string
  defect: Record<string, unknown>
}) {
  const media = editorSourceType.value === 'photo' ? activePhoto.value : activeRecording.value
  if (!media) return
  try {
    await api.saveGraphicAnnotation({
      mediaAssetId: media.id,
      projectId: media.projectId,
      sessionId: media.sessionId,
      sourceType: editorSourceType.value,
      videoTime: editorVideoTime.value,
      shapes: payload.shapes,
      baseSize: payload.baseSize,
      renderedPng: payload.renderedPng,
      defectType: (payload.defect.defectType as string) || '',
      defectCode: (payload.defect.defectCode as string) || '',
      severity: (payload.defect.severity as string) || '',
      direction: (payload.defect.direction as string) || '',
      position: (payload.defect.position as string) || '',
      note: (payload.defect.note as string) || '',
      distanceM: (payload.defect.distanceM as number) ?? 0
    })
    editorOpen.value = false
    await loadGraphicAnnotations(media.id)
    show('标注已保存')
  } catch (error) {
    show((error as Error).message)
  }
}

async function removeGraphicAnnotation(id: number) {
  try {
    await api.deleteGraphicAnnotation(id)
    const media = activePhoto.value ?? activeRecording.value
    if (media) await loadGraphicAnnotations(media.id)
  } catch (error) {
    show((error as Error).message)
  }
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
    distanceM: distance.value,
    projectName: currentProject.value?.name || '',
    projectLocation: currentProject.value?.location || ''
  })
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
    projectLocation: currentProject.value?.location || ''
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
      if (data.mileageM !== null) distance.value = data.mileageM
    } catch {
      // keep last known distance
    }
  }, 250)
})

onUnmounted(() => {
  if (odometerTimer !== null) window.clearInterval(odometerTimer)
})

// Refresh storage options (incl. currently-mounted USB drives) each time the
// settings page is opened.
watch(page, (value) => {
  if (value === 'settings') {
    loadStorage()
    loadRecordingSettings()
  }
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
        <button :class="{ active: page === 'project' }" @click="page = 'project'">项目</button>
        <button :class="{ active: page === 'console' }" @click="page = 'console'">控制</button>
        <button :class="{ active: page === 'annotate' }" @click="openAnnotate">标注</button>
        <button :class="{ active: page === 'reports' }" @click="loadReports">报告</button>
        <button :class="{ active: page === 'settings' }" @click="page = 'settings'">设置</button>
      </nav>
    </header>

    <main>
      <!-- Console uses v-show (not v-if) so the WebRTC preview stays mounted and
           connected when navigating to other pages, and is instantly there on
           return. -->
      <section v-show="page === 'console'" class="console-page">
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

      <section v-else-if="page === 'annotate'" class="annotate-page">
        <aside class="annotate-list">
          <div class="segmented">
            <button :class="{ active: annotateTab === 'image' }" @click="annotateTab = 'image'">图像</button>
            <button :class="{ active: annotateTab === 'video' }" @click="annotateTab = 'video'">视频</button>
          </div>

          <template v-if="annotateTab === 'image'">
            <p v-if="photos.length === 0" class="annotate-empty">暂无图像</p>
            <button
              v-for="p in photos"
              :key="p.id"
              class="annotate-item"
              :class="{ active: activePhoto?.id === p.id }"
              :disabled="!p.available"
              @click="selectPhoto(p)"
            >
              <span class="annotate-item-name">{{ p.name }}</span>
              <span class="annotate-item-meta">{{ p.capturedAt }} · {{ p.distanceM.toFixed(2) }}m</span>
            </button>
          </template>

          <template v-else>
            <p v-if="recordings.length === 0" class="annotate-empty">暂无录像</p>
            <button
              v-for="rec in recordings"
              :key="rec.id"
              class="annotate-item"
              :class="{ active: activeRecording?.id === rec.id }"
              :disabled="!rec.available"
              @click="selectRecording(rec)"
            >
              <span class="annotate-item-name">{{ rec.name }}</span>
              <span class="annotate-item-meta">{{ rec.capturedAt }}<span v-if="!rec.available"> · 文件缺失</span></span>
            </button>
          </template>
        </aside>

        <div class="annotate-main">
          <!-- Editor overlay -->
          <AnnotationEditor
            v-if="editorOpen"
            :base-image="editorBaseImage"
            @save="saveGraphicAnnotation"
            @cancel="editorOpen = false"
          />

          <!-- Image selected -->
          <template v-else-if="annotateTab === 'image' && activePhoto">
            <img class="annotate-photo" :src="activePhoto.imageUrl || ''" alt="snapshot" />
            <div class="annotate-readout">
              <span>里程：{{ activePhoto.distanceM.toFixed(2) }} m</span>
              <button class="primary-action" @click="annotatePhoto">标注此图</button>
            </div>
            <div class="annotate-markers">
              <h3>已保存标注（{{ graphicAnnotations.length }}）</h3>
              <p v-if="graphicAnnotations.length === 0" class="annotate-empty">暂无标注</p>
              <div v-for="a in graphicAnnotations" :key="a.id" class="annotate-anno">
                <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-thumb" />
                <span class="marker-body">
                  <strong>{{ (a.defect.type as string) || '—' }}</strong>
                  <small>{{ (a.defect.position as string) }} · {{ (a.defect.distanceM as number)?.toFixed?.(2) }}m</small>
                </span>
                <button class="link-danger" @click="removeGraphicAnnotation(a.id)">删除</button>
              </div>
            </div>
          </template>

          <!-- Video selected -->
          <template v-else-if="annotateTab === 'video' && activeRecording">
            <video
              ref="annotateVideo"
              class="annotate-video"
              :src="activeRecording.videoUrl || ''"
              controls
              @timeupdate="onAnnotateTimeUpdate"
              @seeked="onAnnotateTimeUpdate"
            />
            <div class="annotate-readout">
              <span>当前时间：{{ videoCurrentTime.toFixed(1) }}s</span>
              <span>里程：{{ currentMileageM === null ? '—' : currentMileageM.toFixed(2) + ' m' }}</span>
              <button class="primary-action" @click="annotateFrame">标注当前帧</button>
            </div>
            <div class="annotate-markers">
              <h3>已保存标注（{{ graphicAnnotations.length }}）</h3>
              <p v-if="graphicAnnotations.length === 0" class="annotate-empty">暂无标注</p>
              <div v-for="a in graphicAnnotations" :key="a.id" class="annotate-anno">
                <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-thumb" />
                <span class="marker-body">
                  <strong>{{ (a.defect.type as string) || '—' }}</strong>
                  <small>
                    <span v-if="a.videoTime !== null">{{ a.videoTime.toFixed(1) }}s · </span>
                    {{ (a.defect.distanceM as number)?.toFixed?.(2) }}m
                  </small>
                </span>
                <button class="link-danger" @click="removeGraphicAnnotation(a.id)">删除</button>
              </div>
            </div>
          </template>

          <div v-else class="annotate-empty-main">
            请选择左侧{{ annotateTab === 'image' ? '图像' : '录像' }}开始标注
          </div>
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

          <article class="settings-card storage-card">
            <h2>存储路径</h2>
            <p class="storage-current">
              当前：<code>{{ storage?.currentPath || '加载中…' }}</code>
              <span v-if="storage && !storage.usingDefault" class="storage-tag">外部</span>
              <span v-else-if="storage" class="storage-tag">内部</span>
            </p>
            <p class="storage-hint">切换后需重启后端生效；旧文件保留在原路径，不会迁移。</p>

            <div class="storage-list" v-if="storage">
              <button
                class="storage-option"
                :class="{ active: storage.currentPath === storage.internal.path }"
                :disabled="storageBusy"
                @click="applyStorage(null)"
              >
                <span class="storage-option-main">内部存储</span>
                <span class="storage-option-path">{{ storage.internal.path }}</span>
                <span class="storage-option-meta">剩余 {{ formatBytes(storage.internal.freeBytes) }}</span>
              </button>

              <button
                v-for="drive in storage.removable"
                :key="drive.path"
                class="storage-option"
                :class="{ active: storage.currentPath === drive.path }"
                :disabled="storageBusy || !drive.writable"
                @click="applyStorage(drive.path)"
              >
                <span class="storage-option-main">{{ drive.label }} <span v-if="!drive.writable" class="storage-ro">只读</span></span>
                <span class="storage-option-path">{{ drive.path }}</span>
                <span class="storage-option-meta">剩余 {{ formatBytes(drive.freeBytes) }}</span>
              </button>

              <p v-if="storage.removable.length === 0" class="storage-empty">未检测到外部存储（U盘）</p>
            </div>

            <label class="storage-manual">
              <span>手动指定路径</span>
              <input v-model="storageManualPath" placeholder="/mnt/usb" :disabled="storageBusy" />
            </label>
            <div class="control-row">
              <button :disabled="storageBusy || !storageManualPath.trim()" @click="applyStorage(storageManualPath.trim())">保存路径</button>
              <button :disabled="storageBusy" @click="loadStorage">刷新</button>
            </div>
          </article>

          <article class="settings-card">
            <h2>录像设置</h2>
            <label>
              <span>分段时长（分钟）</span>
              <input v-model.number="segmentMinutes" type="number" min="1" step="1" />
            </label>
            <p class="storage-hint">每段录像达到该时长后自动切分为新文件。</p>
            <div class="control-row">
              <button @click="saveRecordingSettings">保存</button>
            </div>
          </article>
        </div>
      </section>
    </main>

    <div v-if="notice" class="toast">{{ notice }}</div>
  </div>
</template>
