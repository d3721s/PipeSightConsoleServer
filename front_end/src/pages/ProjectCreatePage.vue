<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CvTile, CvTextInput, CvButton } from '@carbon/vue'
import { ArrowRight24 } from '@carbon/icons-vue'
import { createProjectWithSession, notify } from '../stores/session'

const router = useRouter()
const busy = ref(false)

const form = reactive({
  name: '',
  fanModel: '',
  fanNo: '',
  bladeModel: '',
  bladeLength: '',
  bladeFactoryNo: '',
  location: ''
})

const fields: { key: keyof typeof form; label: string; placeholder?: string }[] = [
  { key: 'name', label: '项目名称', placeholder: '请输入项目名称' },
  { key: 'fanModel', label: '风机机型' },
  { key: 'fanNo', label: '风机编号' },
  { key: 'bladeModel', label: '叶片型号' },
  { key: 'bladeLength', label: '叶片长度' },
  { key: 'bladeFactoryNo', label: '叶片出厂编号' },
  { key: 'location', label: '地点' }
]

async function submit() {
  if (!form.name.trim()) {
    notify('请填写项目名称', 'warning')
    return
  }
  busy.value = true
  try {
    await createProjectWithSession({ ...form })
    notify('项目已创建', 'success')
    router.push('/console')
  } catch (e) {
    notify((e as Error).message, 'error')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page form-page">
    <header class="page-head">
      <h1>风电机组叶片信息收集表</h1>
      <p class="page-sub">填写本次巡检的机组与叶片信息，提交后进入实时巡检</p>
    </header>

    <cv-tile class="form-tile">
      <div class="form-grid">
        <cv-text-input
          v-for="f in fields"
          :key="f.key"
          v-model="form[f.key]"
          :label="f.label"
          :placeholder="f.placeholder || ''"
        />
      </div>
      <div class="form-actions">
        <cv-button size="lg" kind="ghost" @click="router.push('/')">返回首页</cv-button>
        <cv-button size="lg" :icon="ArrowRight24" :disabled="busy" @click="submit">开始巡检</cv-button>
      </div>
    </cv-tile>
  </div>
</template>

<style scoped>
.form-page {
  max-width: 90rem;
  margin: 0 auto;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem 1.75rem;
}
.form-grid :deep(.cv-text-input):first-child {
  grid-column: 1 / -1;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 2.5rem;
}
</style>
