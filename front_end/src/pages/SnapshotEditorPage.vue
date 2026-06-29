<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { CvTabs, CvTab, CvButton, CvTag, CvTile, CvModal } from '@carbon/vue'
import { Image24, VideoFilled24, CubeView24, Download24, Edit24, TrashCan16, TrashCan24, Calculator24, Maximize24, Minimize24 } from '@carbon/icons-vue'
import AnnotationEditor from '../components/AnnotationEditor.vue'
import { api } from '../api'
import { notify } from '../stores/session'
import { decodeDepthRaw, type DepthFrame } from '../utils/depthArea'
import type { GraphicAnnotation, Photo, Recording, TrackData } from '../types'

type Tab = 'image' | 'video' | '3d'
type MileagePair = { left: number | null; right: number | null }
const tab = ref<Tab>('image')

// Maximize the preview/editor: collapse the media rail and let the image area
// fill the whole page so large inspection images can be seen / annotated big.
const maximized = ref(false)

const photos = ref<Photo[]>([])
const recordings = ref<Recording[]>([])
const activePhoto = ref<Photo | null>(null)
const activeRecording = ref<Recording | null>(null)
const track = ref<TrackData | null>(null)
const graphicAnnotations = ref<GraphicAnnotation[]>([])

// Depth snapshots (3D tab) carry a raw-depth blob for area measurement; plain
// photos (image tab) do not. Split the one /photos list by that flag.
const imagePhotos = computed(() => photos.value.filter((p) => !p.isDepth))
const depthPhotos = computed(() => photos.value.filter((p) => p.isDepth))
const activeDepthFrame = ref<DepthFrame | null>(null)
const depthLoading = ref(false)

const annotateVideo = ref<HTMLVideoElement | null>(null)
const videoCurrentTime = ref(0)

const editorOpen = ref(false)
const editorBaseImage = ref('')
const editorSourceType = ref<Tab>('image')
const editorVideoTime = ref<number | null>(null)

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function mileagePair(left: unknown, right: unknown): MileagePair {
  return {
    left: toFiniteNumber(left),
    right: toFiniteNumber(right)
  }
}

function formatMileagePair(pair: MileagePair): string {
  if (pair.left === null && pair.right === null) return '--'
  const left = pair.left === null ? '--' : `${pair.left.toFixed(2)}m`
  const right = pair.right === null ? '--' : `${pair.right.toFixed(2)}m`
  return `${left}-${right}`
}

function photoMileagePair(photo: Photo | null): MileagePair {
  if (!photo) return { left: null, right: null }
  return mileagePair(photo.leftMileage, photo.rightMileage)
}

function recordingMileagePair(recording: Recording | null): MileagePair {
  if (!recording) return { left: null, right: null }
  return mileagePair(recording.leftMileage, recording.rightMileage)
}

function rawNumber(raw: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = toFiniteNumber(raw[key])
    if (value !== null) return value
  }
  return null
}

function sampleMileagePair(raw: Record<string, unknown>): MileagePair {
  return mileagePair(
    rawNumber(raw, ['leftMileage', 'left_mileage']),
    rawNumber(raw, ['rightMileage', 'right_mileage'])
  )
}

function defectMileagePair(defect: Record<string, unknown>): MileagePair {
  return mileagePair(defect.leftMileage, defect.rightMileage)
}

function defectAreaText(defect: Record<string, unknown>): string | null {
  const m2 = toFiniteNumber(defect.areaM2)
  if (m2 === null) return null
  return m2 < 0.01 ? `${(m2 * 1e4).toFixed(1)} cm²` : `${m2.toFixed(4)} m²`
}

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
  tab.value = index === 0 ? 'image' : index === 1 ? 'video' : '3d'
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

// Mileage nearest the current video position.
const currentMileage = computed<MileagePair>(() => {
  const samples = track.value?.samples
  if (!samples || samples.length === 0) return recordingMileagePair(activeRecording.value)
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
  return sampleMileagePair(best.raw)
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

// 3D tab: select a depth snapshot and load its raw depth (for area measurement).
async function selectDepth(photo: Photo) {
  if (!photo.available) return
  activePhoto.value = photo
  activeRecording.value = null
  editorOpen.value = false
  activeDepthFrame.value = null
  await loadAnnotations(photo.id)
  if (!photo.depthDataUrl) return
  depthLoading.value = true
  try {
    const resp = await fetch(photo.depthDataUrl)
    if (!resp.ok) throw new Error('深度数据加载失败')
    activeDepthFrame.value = decodeDepthRaw(await resp.arrayBuffer())
    if (!activeDepthFrame.value) notify('深度数据无法解析，无法测量面积', 'warning')
  } catch (e) {
    notify((e as Error).message || '深度数据加载失败', 'error')
  } finally {
    depthLoading.value = false
  }
}

// Open the editor in measure mode for the selected depth snapshot.
function measureDepth() {
  if (!activePhoto.value?.imageUrl) return
  if (!activeDepthFrame.value) {
    notify('该快照没有可用的深度数据', 'warning')
    return
  }
  editorSourceType.value = 'image'
  editorBaseImage.value = activePhoto.value.imageUrl
  editorVideoTime.value = null
  editorOpen.value = true
}

function downloadPhoto() {
  const photo = activePhoto.value
  if (!photo?.imageUrl) return
  const link = document.createElement('a')
  link.href = photo.imageUrl
  link.download = photo.name || 'snapshot.png'
  document.body.appendChild(link)
  link.click()
  link.remove()
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

const editorMileage = computed<MileagePair>(() =>
  editorSourceType.value === 'image' ? photoMileagePair(activePhoto.value) : currentMileage.value
)

async function saveGraphicAnnotation(payload: {
  shapes: unknown[]
  baseSize: { w: number; h: number }
  renderedPng: string
  defect: Record<string, unknown>
}) {
  const media = editorSourceType.value === 'image' ? activePhoto.value : activeRecording.value
  if (!media) return
  const leftMileage = toFiniteNumber(payload.defect.leftMileage)
  const rightMileage = toFiniteNumber(payload.defect.rightMileage)
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
      leftMileage,
      rightMileage,
      areaM2: toFiniteNumber(payload.defect.areaM2)
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

// --- Delete the selected media (photo / recording) -------------------------
const confirmVisible = ref(false)
const pendingDelete = ref<Photo | Recording | null>(null)
const deleting = ref(false)

function askDeleteMedia(media: Photo | Recording | null) {
  if (!media) return
  pendingDelete.value = media
  confirmVisible.value = true
}

async function confirmDeleteMedia() {
  const media = pendingDelete.value
  if (!media || deleting.value) return
  deleting.value = true
  try {
    await api.deleteMedia(media.id)
    confirmVisible.value = false
    pendingDelete.value = null
    activePhoto.value = null
    activeRecording.value = null
    editorOpen.value = false
    graphicAnnotations.value = []
    await reload()
    notify(tab.value === 'image' ? '图片已删除' : '视频已删除', 'success')
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="annotate-page" :class="{ maximized }">
    <!-- Left: media list -->
    <aside class="media-rail">
      <cv-tabs aria-label="标注来源" @tab-selected="onTabSelected">
        <cv-tab label="图像">
          <div class="media-list">
            <p v-if="imagePhotos.length === 0" class="empty">暂无图像</p>
            <button
              v-for="p in imagePhotos"
              :key="p.id"
              class="media-item"
              :class="{ active: activePhoto?.id === p.id, disabled: !p.available }"
              :disabled="!p.available"
              @click="selectPhoto(p)"
            >
              <span class="media-item-name">{{ p.name }}</span>
              <span class="media-item-meta">{{ p.capturedAt }} · {{ formatMileagePair(photoMileagePair(p)) }}</span>
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
        <cv-tab label="3D">
          <div class="media-list">
            <p v-if="depthPhotos.length === 0" class="empty">暂无深度快照</p>
            <button
              v-for="p in depthPhotos"
              :key="p.id"
              class="media-item"
              :class="{ active: activePhoto?.id === p.id, disabled: !p.available }"
              :disabled="!p.available"
              @click="selectDepth(p)"
            >
              <span class="media-item-name">{{ p.name }}</span>
              <span class="media-item-meta">{{ p.capturedAt }} · {{ formatMileagePair(photoMileagePair(p)) }}</span>
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
        :initial-left-mileage="editorMileage.left"
        :initial-right-mileage="editorMileage.right"
        :depth-frame="tab === '3d' ? activeDepthFrame : null"
        :maximized="maximized"
        @save="saveGraphicAnnotation"
        @cancel="editorOpen = false"
        @toggle-maximize="maximized = !maximized"
      />

      <template v-else-if="tab === 'image' && activePhoto">
        <div class="preview-wrap">
          <img class="preview-img" :src="activePhoto.imageUrl || ''" alt="snapshot" />
        </div>
        <div class="preview-bar">
          <cv-tag kind="cool-gray" :label="`里程 ${formatMileagePair(photoMileagePair(activePhoto))}`" />
          <span class="preview-bar-spacer" />
          <cv-button
            kind="ghost"
            :icon="maximized ? Minimize24 : Maximize24"
            @click="maximized = !maximized"
          >{{ maximized ? '还原' : '最大化' }}</cv-button>
          <cv-button kind="tertiary" :icon="Download24" @click="downloadPhoto">下载图片</cv-button>
          <cv-button :icon="Edit24" @click="annotatePhoto">标注此图</cv-button>
          <cv-button kind="danger--ghost" :icon="TrashCan24" @click="askDeleteMedia(activePhoto)">删除此图</cv-button>
        </div>
        <div class="anno-saved">
          <h3>已保存标注（{{ graphicAnnotations.length }}）</h3>
          <p v-if="graphicAnnotations.length === 0" class="empty">暂无标注</p>
          <cv-tile v-for="a in graphicAnnotations" :key="a.id" class="anno-row">
            <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-thumb" />
            <div class="anno-body">
              <strong>{{ (a.defect.type as string) || '—' }}</strong>
              <small>{{ (a.defect.position as string) }} · 里程 {{ formatMileagePair(defectMileagePair(a.defect)) }}</small>
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
          <cv-tag kind="cool-gray" :label="`里程 ${formatMileagePair(currentMileage)}`" />
          <span class="preview-bar-spacer" />
          <cv-button
            kind="ghost"
            :icon="maximized ? Minimize24 : Maximize24"
            @click="maximized = !maximized"
          >{{ maximized ? '还原' : '最大化' }}</cv-button>
          <cv-button :icon="Edit24" @click="annotateFrame">标注当前帧</cv-button>
          <cv-button kind="danger--ghost" :icon="TrashCan24" @click="askDeleteMedia(activeRecording)">删除此视频</cv-button>
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
                里程 {{ formatMileagePair(defectMileagePair(a.defect)) }}
              </small>
            </div>
            <cv-button kind="danger--ghost" size="sm" :icon="TrashCan16" @click="removeAnnotation(a.id)" />
          </cv-tile>
        </div>
      </template>

      <template v-else-if="tab === '3d' && activePhoto">
        <div class="preview-wrap">
          <img class="preview-img" :src="activePhoto.imageUrl || ''" alt="depth snapshot" />
        </div>
        <div class="preview-bar">
          <cv-tag kind="cool-gray" :label="`里程 ${formatMileagePair(photoMileagePair(activePhoto))}`" />
          <cv-tag v-if="depthLoading" kind="blue" label="深度加载中…" />
          <cv-tag v-else-if="!activeDepthFrame" kind="red" label="无深度数据" />
          <span class="preview-bar-spacer" />
          <cv-button
            kind="ghost"
            :icon="maximized ? Minimize24 : Maximize24"
            @click="maximized = !maximized"
          >{{ maximized ? '还原' : '最大化' }}</cv-button>
          <cv-button
            :icon="Calculator24"
            :disabled="!activeDepthFrame"
            @click="measureDepth"
          >框选计算面积</cv-button>
          <cv-button kind="danger--ghost" :icon="TrashCan24" @click="askDeleteMedia(activePhoto)">删除此快照</cv-button>
        </div>
        <div class="anno-saved">
          <h3>已保存测量（{{ graphicAnnotations.length }}）</h3>
          <p v-if="graphicAnnotations.length === 0" class="empty">暂无测量</p>
          <cv-tile v-for="a in graphicAnnotations" :key="a.id" class="anno-row">
            <img v-if="a.renderedUrl" :src="a.renderedUrl" class="anno-thumb" />
            <div class="anno-body">
              <strong>{{ defectAreaText(a.defect) || (a.defect.type as string) || '面积测量' }}</strong>
              <small>
                <span v-if="defectAreaText(a.defect) && (a.defect.type as string)">{{ a.defect.type }} · </span>
                里程 {{ formatMileagePair(defectMileagePair(a.defect)) }}
              </small>
            </div>
            <cv-button kind="danger--ghost" size="sm" :icon="TrashCan16" @click="removeAnnotation(a.id)" />
          </cv-tile>
        </div>
      </template>

      <template v-else-if="tab === '3d'">
        <div class="empty-main">
          <component :is="CubeView24" class="empty-icon" />
          <p>请选择左侧深度快照开始测量</p>
        </div>
      </template>

      <div v-else class="empty-main">
        <component :is="tab === 'image' ? Image24 : VideoFilled24" class="empty-icon" />
        <p>请选择左侧{{ tab === 'image' ? '图像' : '录像' }}开始标注</p>
      </div>
    </section>

    <cv-modal
      kind="danger"
      :visible="confirmVisible"
      :primary-button-disabled="deleting"
      @update:visible="confirmVisible = $event"
      @primary-click="confirmDeleteMedia"
      @secondary-click="confirmVisible = false"
    >
      <template #title>{{ tab === 'image' ? '删除图片' : '删除视频' }}</template>
      <template #content>
        <p>
          确定删除「{{ pendingDelete?.name }}」吗？
          此操作会同时删除该{{ tab === 'image' ? '图片' : '视频' }}文件及其全部标注，且不可恢复。
        </p>
      </template>
      <template #secondary-button>取消</template>
      <template #primary-button>删除</template>
    </cv-modal>
  </div>
</template>

<style scoped>
.annotate-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 3fr);
  gap: 1.5rem;
  height: calc(100vh - 4rem - 5rem);
}
/* Maximize mode: break out of the page chrome into a full-viewport overlay that
   SCROLLS. The image is shown big (most of the viewport height); the form /
   buttons / saved list flow underneath and you scroll down to reach them —
   nothing is squeezed onto one screen or clipped. */
.annotate-page.maximized {
  position: fixed;
  /* Start BELOW the fixed 4rem app header — it has a far higher z-index, so an
     inset:0 overlay would let the header sit on top and hide the toolbar (the
     first element) behind it. */
  top: 4rem;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 50;
  display: block;
  grid-template-columns: none;
  gap: 0;
  height: calc(100vh - 4rem);
  padding: 0.75rem;
  background: #ffffff;
  overflow-y: auto;
}
.annotate-page.maximized .media-rail {
  display: none;
}
/* Plain flow inside the scrolling overlay — no flex height games, no inner
   scroll, so the whole thing scrolls as one page. Drop the panel's own padding
   so the toolbar sits flush at the overlay's top. */
.annotate-page.maximized .annotate-main {
  display: block;
  overflow: visible;
  height: auto;
  padding: 0;
  border: none;
}
/* Big image: use most of the viewport height. It's not forced to fit the whole
   page alongside the form — the page scrolls instead. object-fit: contain keeps
   the full image visible (letterboxed), never cropped. */
.annotate-page.maximized .preview-wrap {
  height: 82vh;
  min-height: 82vh;
  max-height: 82vh;
}
.annotate-page.maximized .preview-img,
.annotate-page.maximized .preview-video {
  max-height: 82vh;
}
/* Editor canvas: big image that fills the viewport below the toolbar. Only the
   toolbar (~5rem) + overlay padding sit above it, so it stays large; the form /
   buttons flow below and scroll into view. */
.annotate-page.maximized :deep(.annot-canvas-wrap) {
  height: calc(100vh - 11rem);
  min-height: calc(100vh - 11rem);
  max-height: calc(100vh - 11rem);
}
.annotate-page.maximized :deep(.annot-canvas-wrap canvas) {
  max-height: calc(100vh - 11rem);
}
.annotate-page.maximized :deep(.annot-editor) {
  height: auto;
  min-height: 0;
}
.media-rail {
  background: #ffffff;
  border: 1px solid #e0e0e0;
  padding: 0.5rem;
  overflow-y: auto;
}
/* Make the 3 source tabs (图像/视频/3D) share the rail width and fit without
   the scrollable-tabs overflow arrow. @carbon/vue renders SCROLLABLE tabs, so
   the classes carry "scrollable" — target those, make the nav full-width with
   equal-width items and tight padding so scrollWidth never exceeds clientWidth
   (which is what triggers Carbon's "›" overflow button). */
.media-rail :deep(.bx--tabs--scrollable__nav) {
  display: flex;
  width: 100%;
}
.media-rail :deep(.bx--tabs--scrollable__nav-item) {
  flex: 1 1 0;
  min-width: 0;
}
.media-rail :deep(.bx--tabs--scrollable__nav-link) {
  width: 100%;
  min-width: 0;
  padding-left: 0.5rem;
  padding-right: 0.5rem;
  text-align: center;
  justify-content: center;
}
/* Hide the left/right scroll arrows entirely — everything fits now. */
.media-rail :deep(.bx--tab--overflow-nav-button) {
  display: none;
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
  /* Grow to fill the space left in the column so the image isn't squeezed into
     a small strip; keep a floor and a generous ceiling. */
  flex: 1 1 auto;
  min-height: 20rem;
  max-height: 78vh;
  overflow: hidden;
}
.preview-img,
.preview-video {
  /* Explicit width: a <video> with only max-* constraints collapses to ~0
     height before metadata loads, making it invisible. */
  width: 100%;
  height: 100%;
  max-height: 78vh;
  object-fit: contain;
}
.preview-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.75rem 0;
}
.preview-bar-spacer {
  flex: 1;
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
