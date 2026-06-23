// Node-runnable test for the shared markdown renderer (run with: node --experimental-strip-types src/utils/markdown.test.mjs).
import md from './markdown.ts'

let passed = 0
let failed = 0
function assert(cond, msg) {
  if (cond) { passed++ } else { failed++; console.error('FAIL:', msg) }
}

// 1. tables are wrapped in the scroll container
{
  const html = md.render('| 展望供应总量 | 供给缺口总量 |\n|---|---|\n| 1 | 2 |\n')
  assert(html.includes('md-table-wrap'), 'table wrapped in scroll container')
  // Styling contract: the wrap is a div directly wrapping the table (relies on the
  // `.md-render-container .md-table-wrap` selector in style.less).
  assert(/class="md-table-wrap"><table>/.test(html), 'table-wrap is a div directly wrapping the table')
  assert(html.includes('<th>'), 'table has header cells')
}

// 2. TOP1 callout renders as a blockquote.
// Styling contract: `.md-render-container blockquote` (the container carries both
// `markdown-body` and `md-render-container` on one element — see MdComponent.vue), so
// visual verification of the callout is done in the browser.
{
  const html = md.render('> 🔴 TOP1：硅胶密封圈 缺口 86795 pcs（>15% 严重）\n')
  assert(html.includes('<blockquote>'), 'TOP1 callout is a blockquote')
  assert(html.includes('🔴 TOP1'), 'TOP1 marker preserved')
}

if (failed === 0) { console.log(`markdown: ${passed} passed`) } else { console.error(`markdown: ${failed} FAILED`); process.exit(1) }
