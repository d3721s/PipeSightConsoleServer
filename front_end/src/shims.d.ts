// Type shims for libraries that ship without (or with broken) Vue 3 typings.

// @carbon/icons-vue ships no type declarations. Declaring the module without a
// body makes every named import (Camera24, Settings24, …) resolve to `any`,
// which is the standard pattern for an untyped module with many named exports.
declare module '@carbon/icons-vue'

// @carbon/vue only declares a default export (the plugin) and its bundled .d.ts
// references a Vue-2-only type. The Cv* components are registered globally by
// `app.use(CarbonVue3)`, but we import a few as values; declare them loosely.
declare module '@carbon/vue' {
  import type { Component, Plugin } from 'vue'
  const CarbonVue3: Plugin
  export default CarbonVue3
  export const CvHeader: Component
  export const CvHeaderName: Component
  export const CvHeaderNav: Component
  export const CvHeaderMenuItem: Component
  export const CvContent: Component
  export const CvButton: Component
  export const CvTile: Component
  export const CvTextInput: Component
  export const CvNumberInput: Component
  export const CvTag: Component
  export const CvTabs: Component
  export const CvTab: Component
  export const CvToastNotification: Component
  export const CvInlineNotification: Component
}
