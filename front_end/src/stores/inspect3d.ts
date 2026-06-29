import { ref, watch } from 'vue'

// View mode for the 三维巡检 page. Lifted out of Inspect3dPage.vue (where it was a
// component-local ref) so that navigating to another page and back keeps the
// last-selected view instead of snapping back to point cloud — the page is
// rendered via <router-view> without keep-alive, so its component is unmounted
// on navigation and any local ref would reset to its default.

export type ViewMode = 'pointcloud' | 'depth' | 'rgb' | 'infrared'

const VIEW_MODES: ViewMode[] = ['pointcloud', 'depth', 'rgb', 'infrared']
const LS_VIEW_MODE = 'pipesight.inspect3dViewMode'

function readMode(): ViewMode {
  try {
    const raw = window.localStorage.getItem(LS_VIEW_MODE)
    if (raw && (VIEW_MODES as string[]).includes(raw)) return raw as ViewMode
  } catch {
    // Ignore storage failures; fall back to the default.
  }
  return 'pointcloud'
}

// Persist to localStorage too, matching the session store, so the chosen view
// also survives a full browser refresh.
export const inspect3dViewMode = ref<ViewMode>(readMode())

watch(inspect3dViewMode, (m) => {
  try {
    window.localStorage.setItem(LS_VIEW_MODE, m)
  } catch {
    // Ignore storage failures; in-memory state still works this session.
  }
})
