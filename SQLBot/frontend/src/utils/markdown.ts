import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

// Single shared renderer used by every answer surface (analysis, predict,
// thinking, chart summary). Tuned for streaming Markdown business reports:
// no typographic mangling of CJK punctuation, auto-linked URLs, safe new-tab
// links, horizontally scrollable tables, and correctly structured code blocks.
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
  highlight(str, lang) {
    const language = lang && hljs.getLanguage(lang) ? lang : ''
    let highlighted: string
    if (language) {
      try {
        highlighted = hljs.highlight(str, { language, ignoreIllegals: true }).value
      } catch (e) {
        console.error(e)
        highlighted = md.utils.escapeHtml(str)
      }
    } else {
      highlighted = md.utils.escapeHtml(str)
    }

    // NOTE: keep this on a single line. <pre> preserves whitespace literally,
    // so any newline/indentation here would show up as a leading blank line and
    // indentation inside every code block (the bug this replaced).
    const langClass = language ? ` language-${language}` : ''
    return `<pre><code class="hljs${langClass}">${highlighted}</code></pre>`
  },
})

// Open every link in a new tab, with safe rel attributes.
const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const setAttr = (name: string, value: string) => {
    const i = tokens[idx].attrIndex(name)
    if (i < 0) tokens[idx].attrPush([name, value])
    else tokens[idx].attrs![i][1] = value
  }
  setAttr('target', '_blank')
  setAttr('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

// Wrap tables in a scroll container so wide tables don't overflow the chat card.
md.renderer.rules.table_open = () => '<div class="md-table-wrap"><table>'
md.renderer.rules.table_close = () => '</table></div>'

export default md
