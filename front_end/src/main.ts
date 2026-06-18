import { createApp } from 'vue'
import CarbonVue3 from '@carbon/vue'
import App from './App.vue'
import { router } from './router'
// Carbon 10's fully-compiled stylesheet (the @carbon/vue dist css is empty; the
// real component CSS ships in carbon-components, a dependency of @carbon/vue).
// Shipped precompiled so we don't need a Sass toolchain in the Vite build.
import 'carbon-components/css/carbon-components.min.css'
import './styles.css'

// Disable browser context menus, text selection handles, and drag affordances
// app-wide for kiosk/tablet use.
const suppressBrowserGesture = (event: Event) => event.preventDefault()
window.addEventListener('contextmenu', suppressBrowserGesture)
document.addEventListener('selectstart', suppressBrowserGesture)
document.addEventListener('dragstart', suppressBrowserGesture)

const PINCH_ZOOM_SURFACE_SELECTOR = '.pinch-zoom-surface'

function isInPinchZoomSurface(target: EventTarget | null) {
  return target instanceof Element && target.closest(PINCH_ZOOM_SURFACE_SELECTOR) !== null
}

function touchIsInPinchZoomSurface(touch: Touch) {
  return isInPinchZoomSurface(document.elementFromPoint(touch.clientX, touch.clientY))
}

function suppressPagePinch(event: TouchEvent) {
  if (event.touches.length < 2) return
  if (Array.from(event.touches).every(touchIsInPinchZoomSurface)) return
  if (event.cancelable) event.preventDefault()
}

function suppressPageGesture(event: Event) {
  if (isInPinchZoomSurface(event.target)) return
  if (event.cancelable) event.preventDefault()
}

document.addEventListener('touchstart', suppressPagePinch, { passive: false })
document.addEventListener('touchmove', suppressPagePinch, { passive: false })
document.addEventListener('gesturestart', suppressPageGesture, { passive: false })
document.addEventListener('gesturechange', suppressPageGesture, { passive: false })

createApp(App).use(CarbonVue3).use(router).mount('#app')
