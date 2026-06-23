import { createApp } from 'vue'
import { createPinia } from 'pinia'
// Import the third-party Markdown/code styles BEFORE our style.less so that our
// tighter chat-card typography overrides (equal specificity) win the cascade.
import 'highlight.js/styles/github.min.css'
import 'github-markdown-css/github-markdown-light.css'
import './style.less'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import VueDOMPurifyHTML from 'vue-dompurify-html'

// import 'element-plus/dist/index.css'
const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(i18n)
app.use(VueDOMPurifyHTML, {
  default: {
    // Allow links rendered from Markdown answers to open in a new tab.
    ADD_ATTR: ['target'],
  },
})
app.mount('#app')
