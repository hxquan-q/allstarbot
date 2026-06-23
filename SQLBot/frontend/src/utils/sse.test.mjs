// Node-runnable test for the SSE parser (run with: node --experimental-strip-types sse.test.mjs).
// Uses dynamic import of the .ts source via node's strip-types (node >= 22.6).
import { extractSSEFrames } from './sse.ts'

let passed = 0
let failed = 0
function assert(cond, msg) {
  if (cond) { passed++ } else { failed++; console.error('FAIL:', msg) }
}

const parse = (raw) => JSON.parse(raw)

// 1. single complete frame
{
  const r = extractSSEFrames('data: {"type":"sql","sql":"SELECT 1"}\n\n')
  assert(r.frames.length === 1, 'single frame: one frame')
  assert(r.remainder === '', 'single frame: empty remainder')
  assert(parse(r.frames[0]).sql === 'SELECT 1', 'single frame: payload')
}

// 2. TWO frames in one buffer — the greedy regex bug. Must yield both.
{
  const r = extractSSEFrames('data: {"type":"a"}\n\ndata: {"type":"b"}\n\n')
  assert(r.frames.length === 2, 'two frames: both parsed (was the greedy-regex bug)')
  assert(parse(r.frames[0]).type === 'a' && parse(r.frames[1]).type === 'b', 'two frames: order preserved')
  assert(r.remainder === '', 'two frames: empty remainder')
}

// 3. partial frame (no closing blank line) → carried as remainder, 0 frames
{
  const buf = 'data: {"type":"partial"'
  const r = extractSSEFrames(buf)
  assert(r.frames.length === 0, 'partial frame: no frames')
  assert(r.remainder === buf, 'partial frame: carried over')
}

// 4. chunk carry-over: first chunk partial, second completes the frame
{
  let buffer = 'data: {"type":"sql","sql":"SEL'
  let r = extractSSEFrames(buffer)
  assert(r.frames.length === 0 && r.remainder === buffer, 'carry: first chunk held')
  buffer = r.remainder + 'ECT 1"}\n\n'
  r = extractSSEFrames(buffer)
  assert(r.frames.length === 1, 'carry: completed on second chunk')
  assert(parse(r.frames[0]).sql === 'SELECT 1', 'carry: payload correct')
}

// 5. delimiter guard: two frames back-to-back must not mis-split
{
  const r = extractSSEFrames('data: {"note":"end of frame here"}\n\ndata: {"type":"next"}\n\n')
  assert(r.frames.length === 2, 'delimiter guard: two frames, no mis-split')
}

// 6. no space after data:
{
  const r = extractSSEFrames('data:{"type":"compact"}\n\n')
  assert(r.frames.length === 1 && parse(r.frames[0]).type === 'compact', 'no space after data:')
}

// 7. raw strings preserve BigInt-safe parsing at the call site
{
  const r = extractSSEFrames('data: {"id":9223372036854775807}\n\n')
  // raw string round-trips; caller decides JSON vs JSONBig
  assert(r.frames[0] === '{"id":9223372036854775807}', 'raw payload preserved verbatim')
}

// 8. empty buffer
{
  const r = extractSSEFrames('')
  assert(r.frames.length === 0 && r.remainder === '', 'empty buffer')
}

console.log(`\n${passed} passed, ${failed} failed`)
if (failed > 0) process.exit(1)
