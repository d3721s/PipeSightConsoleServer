import { createApp } from 'vue'
import CarbonVue3 from '@carbon/vue'
import App from './App.vue'
import { router } from './router'
// Carbon 10's fully-compiled stylesheet (the @carbon/vue dist css is empty; the
// real component CSS ships in carbon-components, a dependency of @carbon/vue).
// Shipped precompiled so we don't need a Sass toolchain in the Vite build.
import 'carbon-components/css/carbon-components.min.css'
import './styles.css'

// Disable the browser right-click context menu app-wide (kiosk/tablet use).
window.addEventListener('contextmenu', (event) => event.preventDefault())

createApp(App).use(CarbonVue3).use(router).mount('#app')
