/**
 * Incremental Server-Sent Events parser for the chat stream.
 *
 * Replaces the greedy `/data:.*}\n\n/g` regex used in the answer components.
 * That regex is greedy across the whole buffer, so when two frames share a
 * buffer — `data:{a}\n\ndata:{b}\n\n` — it matched the entire span as one,
 * silently dropping the second frame; and a JSON string value containing `}`
 * followed by a blank line corrupted the split.
 *
 * This parser follows the SSE spec properly: frames are delimited by a blank
 * line (`\n\n`); we find the *first* delimiter, slice off one complete frame,
 * collect its `data:` lines, and keep the leftover tail to carry into the
 * next chunk. It returns the raw `data:` payload strings (not parsed JSON) so
 * each caller can use its own parser — ChartAnswer needs BigInt-safe
 * `JSONBig.parse` for streamed 64-bit ids, the other answers use `JSON.parse`.
 *
 * Pure and side-effect free → unit-testable in isolation.
 */

export interface SSEParseResult {
  /** Raw `data:` payloads of all complete frames found in the buffer. */
  frames: string[]
  /** The incomplete trailing bytes to prepend to the next chunk. */
  remainder: string
}

/**
 * Extract complete SSE frames from a buffer string.
 *
 * Call repeatedly, feeding `remainder` back as the start of the next buffer:
 *
 * ```ts
 * let buffer = ''
 * buffer += chunk
 * const { frames, remainder } = extractSSEFrames(buffer)
 * for (const raw of frames) handleEvent(JSON.parse(raw)) // or JSONBig.parse
 * buffer = remainder
 * ```
 */
export function extractSSEFrames(buffer: string): SSEParseResult {
  const frames: string[] = []
  let rest = buffer

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const delimiter = rest.indexOf('\n\n')
    if (delimiter === -1) break

    const frame = rest.slice(0, delimiter)
    rest = rest.slice(delimiter + 2)

    const dataLines = frame
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^\s/, ''))

    if (dataLines.length === 0) continue

    frames.push(dataLines.join('\n'))
  }

  return { frames, remainder: rest }
}

