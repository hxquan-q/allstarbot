// g2-ssr: echarts node 出图服务。POST 契约 {path, type, data, axis}（data/axis 为 JSON 字符串）
// 出图逻辑见 render.cjs（与前端 buildEChartsOption 共用同一 builder）
const http = require('http')
const url = require('url')
const util = require('util')
const { render } = require('./render.cjs')

const PORT = 3000

http.createServer((req, res) => {
  res.statusCode = 200
  res.setHeader('Content-Type', 'text/plain;charset=utf-8')
  if (req.method === 'GET') return toGet(req, res)
  if (req.method === 'POST') return toPost(req, res)
  res.end()
}).listen(PORT, () => console.info(`Server listening on: http://localhost:${PORT}`))

function toGet(req, res) {
  res.end('GET请求内容：\n' + util.inspect(url.parse(req.url)))
}

function toPost(req, res) {
  const chunks = []
  req.on('data', (c) => chunks.push(c))
  req.on('end', () => {
    try {
      const obj = JSON.parse(Buffer.concat(chunks).toString('utf8'))
      render(obj)
      res.end('complete')
    } catch (e) {
      // 旧码无错误处理，坏 payload 会崩 pm2 worker
      console.error(e)
      res.statusCode = 500
      res.end('error: ' + ((e && e.message) || e))
    }
  })
}
