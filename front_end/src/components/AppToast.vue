<script setup lang="ts">
import { CvToastNotification } from '@carbon/vue'
import { clearNotice, notice } from '../stores/session'
</script>

<template>
  <transition name="toast-fade">
    <cv-toast-notification
      v-if="notice"
      class="app-toast"
      :kind="notice.kind"
      :title="notice.text"
      sub-title=""
      caption=""
      @close="clearNotice"
    />
  </transition>
</template>

<style scoped>
.app-toast {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 9000;
  min-width: 18rem;
}
/* Carbon's toast status icon + close button use fixed-px SVGs that don't track
   our enlarged root font, so they look tiny on the tablet. Scale them up and
   give the close button a comfortable tap target. */
.app-toast :deep(.bx--toast-notification__icon),
.app-toast :deep(.bx--toast-notification__close-icon) {
  width: 1.5rem;
  height: 1.5rem;
}
.app-toast :deep(.bx--toast-notification__close-button) {
  width: 3rem;
  height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
