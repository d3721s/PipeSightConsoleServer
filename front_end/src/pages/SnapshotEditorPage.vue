<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { CvTabs, CvTab, CvButton, CvTag, CvTile } from '@carbon/vue'
import { Image24, VideoFilled24, Edit24, TrashCan16 } from '@carbon/icons-vue'
import AnnotationEditor from '../components/AnnotationEditor.vue'
import { api } from '../api'
import { notify } from '../stores/session'
import type { GraphicAnnotation, Photo, Recording, TrackData } from '../types'

type Tab = 'image' | 'video'
const tab = ref<Tab>('image')

const photos = ref<Photo[]>([])
const recordings = ref<Recording[]>([])
const activePhoto = ref<Photo | null>(null)
const activeRecording = ref<Recording | null>(null)
const track = ref<TrackData | null>(null)
const graphicAnnotations = ref<GraphicAnnotation[]>([])

const annotateVideo = ref<HTMLVideoElement | null>(null)
const videoCurrentTime = ref(0)

const editorOpen = ref(false)
const editorBaseImage = ref('')
const editorSourceType = ref<Tab>('image')
const editorVideoTime = ref<number | null>(null)

async function reload() {
  try {
    const [pics, recs] = await Promise.all([api.listPhotos(), api.listRecordings()])
    photos.value = pics
    recordings.value = recs
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

onMounted(reload)
onActivated(reload)

function onTabSelected(index: number) {
  tab.value = index === 0 ? 'image' : 'video'
}

async function loadAnnotations(mediaId: number) {
  try {
    graphicAnnotations.value = await api.listGraphicAnnotations(mediaId)
  } catch {
    graphicAnnotations.value = []
  }
}

async function selectPhoto(photo: Photo) {
  if (!photo.available) return
  activePhoto.value = photo
  activeRecording.value = null
  editorOpen.value = false
  await loadAnnotations(photo.id)
}

async function selectRecording(rec: Recording) {
  if (!rec.available) return
  activeRecording.value = rec
  activePhoto.value = null
  editorOpen.value = false
  track.value = null
  videoCurrentTime.value = 0
  try {
    track.value = await api.recordingTrack(rec.id)
  } catch (e) {
    notify((e as Error).message, 'error')
  }
  await loadAnnotations(rec.id)
}

// Mileage (m) nearest the current video position.
const currentMileageM = computed(() => {
  const samples = track.value?.samples
  if (!samples || samples.length === 0) return null
  const t = videoCurrentTime.value
  let best = samples[0]
  let bestDelta = Math.abs(best.videoTime - t)
  for (const s of samples) {
    const d = Math.abs(s.videoTime - t)
    if (d < bestDelta) {
      best = s
      bestDelta = d
    }
  }
  const cm = best.raw?.mileage_cm
  return typeof cm === 'number' ? cm / 100 : null
})

function onTimeUpdate() {
  if (annotateVideo.value) videoCurrentTime.value = annotateVideo.value.currentTime
}

function annotatePhoto() {
  if (!activePhoto.value?.imageUrl) return
  editorSourceType.value = 'image'
  editorBaseImage.value = activePhoto.value.imageUrl
  editorVideoTime.value = null
  editorOpen.value = true
}

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
  editorOpen.value = true
}

const editorDistance = computed(() =>
  editorSourceType.value === 'image' ? activePhoto.value?.distanceM ?? 0 : currentMileageM.value ?? 0
)

async function saveGraphicAnnotation(payload: {
  shapes: unknown[]
  baseSize: { w: number; h: number }
  renderedPng: string
  defect: Record<string, unknown>
}) {
  const media = editorSourceType.value === 'image' ? activePhoto.value : activeRecording.value
  if (!media) return
  try {
    await api.saveGraphicAnnotation({
      mediaAssetId: media.id,
      projectId: media.projectId,
      sessionId: media.sessionId,
      sourceType: editorSourceType.value === 'image' ? 'photo' : 'video',
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
    await loadAnnotations(media.id)
    notify('标注已保存', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}

async function removeAnnotation(id: number) {
  try {
    await api.deleteGraphicAnnotation(id)
    const media = activePhoto.value ?? activeRecording.value
    if (media) await loadAnnotations(media.id)
    notify('标注已删除', 'info')
  } catch (e) {
    notify((e as Error).message, 'error')
  }
}
</script>

<template>
  <div class="annotate-page">
    <!-- Left: media list -->
    <aside class="media-rail">
      <cv-tabs aria-label="标注来源" @tab-selected="onTabSelected">
        <cv-tab label="图像">
          <div class="media-list">
            <p v-if="photos.length === 0" class="empty">暂无图像</p>
            <button
              v-for="p in photos"
              :key="p.id"
              class="media-item"
              :class="{ active: activePhoto?.id === p.id, disabled: !p.available }"
              :disabled="!p.available"
              @click="selectPhoto(p)"
            >
              <span class="media-item-name">{{ p.name }}</span>
              <span class="media-item-meta">{{ p.capturedAt }} · {{ p.distanceM.toFixed(2) }} m</span>
            </button>
          </div>
        </cv-tab>
        <cv-tab label="视频">
          <div class="media-list">
            <p v-if="recordings.length === 0" class="empty">暂无录像</p>
            <button
              v-for="rec in recordings"
              :key="rec.id"
              class="media-item"
              :class="{ active: activeRecording?.id === rec.id, disabled: !rec.available }"
              :disabled="!rec.available"
              @click="selectRecording(rec)"
            >
              <span class="media-item-name">{{ rec.name }}</span>
              <span class="media-item-meta">
                {{ rec.capturedAt }}<span v-if="!rec.available"> · 文件缺失</span>
              </span>
            </button>
          </div>
        </cv-tab>
      </cv-tabs>
    </aside>

    <!-- Right: editor / preview -->
    <section class="annotate-main">
      <annotation-editor
        v-if="editorOpen"
        :base-image="editorBaseImage"
        :initial-distance="editorDistance"
        @save="saveGraphicAnnotation"
        @cancel="editorOpen = false"
      />

      <template v-else-if="tab === 'image' && activePhoto">
        <div class="preview-wrap">
          <img class="preview-img" :src="activePhoto.imageUrl || ''" alt="snapshot" />
        </div>
        <div class="preview-bar">
          <cv-tag kind="cool-gray" :label="`里程 ${activePhoto.distanceM.toFixed(2)} m`" />
          <cv-button size="sm" :icon="Edit24" @click="annotatePhoto">标注此图</cv-button>
        </div>
        <div class="anno-saved">
          <h3>已保存标注（{{ graphicAnnotations.length }}）</h3>
          <p v-if="graphicAnnotations.length === 0" class="empty">暂无标注</p>
          <cv-tile v-for="a in graphicAnnotations" :key="a.id" class="anno-row">
            <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-thumb" />
            <div class="anno-body">
              <strong>{{ (a.defect.type as string) || '—' }}</strong>
              <small>{{ (a.defect.position as string) }} · {{ (a.defect.distanceM as number)?.toFixed?.(2) }} m</small>
            </div>
            <cv-button kind="danger--ghost" size="sm" :icon="TrashCan16" @click="removeAnnotation(a.id)" />
          </cv-tile>
        </div>
      </template>

      <template v-else-if="tab === 'video' && activeRecording">
        <div class="preview-wrap">
          <video
            ref="annotateVideo"
            class="preview-video"
            :src="activeRecording.videoUrl || ''"
            controls
            @timeupdate="onTimeUpdate"
            @seeked="onTimeUpdate"
          />
        </div>
        <div class="preview-bar">
          <cv-tag kind="cool-gray" :label="`时间 ${videoCurrentTime.toFixed(1)} s`" />
          <cv-tag kind="cool-gray" :label="`里程 ${currentMileageM === null ? '—' : currentMileageM.toFixed(2) + ' m'}`" />
          <cv-button size="sm" :icon="Edit24" @click="annotateFrame">标注当前帧</cv-button>
        </div>
        <div class="anno-saved">
          <h3>已保存标注（{{ graphicAnnotations.length }}）</h3>
          <p v-if="graphicAnnotations.length === 0" class="empty">暂无标注</p>
          <cv-tile v-for="a in graphicAnnotations" :key="a.id" class="anno-row">
            <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-thumb" />
            <div class="anno-body">
              <strong>{{ (a.defect.type as string) || '—' }}</strong>
              <small>
                <span v-if="a.videoTime !== null">{{ a.videoTime.toFixed(1) }} s · </span>
                {{ (a.defect.distanceM as number)?.toFixed?.(2) }} m
              </small>
            </div>
            <cv-button kind="danger--ghost" size="sm" :icon="TrashCan16" @click="removeAnnotation(a.id)" />
          </cv-tile>
        </div>
      </template>

      <div v-else class="empty-main">
        <component :is="tab === 'image' ? Image24 : VideoFilled24" class="empty-icon" />
        <p>请选择左侧{{ tab === 'image' ? '图像' : '录像' }}开始标注</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.annotate-page {
  display: grid;
  grid-template-columns: 24rem 1fr;
  gap: 1.5rem;
  height: calc(100vh - 4rem - 5rem);
}
.media-rail {
  background: #ffffff;
  border: 1px solid #e0e0e0;
  padding: 0.5rem;
  overflow-y: auto;
}
.media-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding-top: 0.5rem;
}
.media-item {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  text-align: left;
  padding: 0.625rem 0.75rem;
  background: #ffffff;
  border: 1px solid transparent;
  border-left: 3px solid transparent;
  color: #161616;
  cursor: pointer;
}
.media-item:hover:not(.disabled) {
  background: #e8e8e8;
}
.media-item.active {
  border-left-color: #0f62fe;
  background: #e0e0e0;
}
.media-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.media-item-name {
  font-size: 0.875rem;
  word-break: break-all;
}
.media-item-meta {
  font-size: 0.75rem;
  color: #6f6f6f;
}
.annotate-main {
  background: #ffffff;
  border: 1px solid #e0e0e0;
  padding: 1rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.preview-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  background: #000;
  border: 1px solid #e0e0e0;
  min-height: 18rem;
  max-height: 60vh;
  overflow: hidden;
}
.preview-img,
.preview-video {
  /* Explicit width: a <video> with only max-* constraints collapses to ~0
     height before metadata loads, making it invisible. */
  width: 100%;
  max-height: 60vh;
  object-fit: contain;
}
.preview-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0;
}
.anno-saved {
  margin-top: 0.5rem;
}
.anno-saved h3 {
  font-size: 1rem;
  margin: 0 0 0.75rem;
}
.anno-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.anno-thumb {
  width: 4rem;
  height: 4rem;
  object-fit: cover;
  border: 1px solid #e0e0e0;
}
.anno-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.anno-body small {
  color: #6f6f6f;
}
.empty {
  color: #6f6f6f;
  padding: 1rem 0.5rem;
  font-size: 0.875rem;
}
.empty-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #6f6f6f;
  gap: 0.75rem;
}
.empty-icon {
  width: 3rem;
  height: 3rem;
  opacity: 0.5;
}
</style>
