import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import {
  ChatDotRound,
  ChatLineRound,
  Checked,
  CollectionTag,
  Comment,
  Connection,
  Cpu,
  DataAnalysis,
  Document,
  FolderOpened,
  Message,
  Microphone,
  Odometer,
  OfficeBuilding,
  Search,
  Setting,
  Stamp,
  Switch,
  UploadFilled,
  User,
  UserFilled,
  VideoCamera,
} from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)

const icons = {
  ChatDotRound,
  ChatLineRound,
  Checked,
  CollectionTag,
  Comment,
  Connection,
  Cpu,
  DataAnalysis,
  Document,
  FolderOpened,
  Message,
  Microphone,
  Odometer,
  OfficeBuilding,
  Search,
  Setting,
  Stamp,
  Switch,
  UploadFilled,
  User,
  UserFilled,
  VideoCamera,
} as const

for (const [key, component] of Object.entries(icons)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
