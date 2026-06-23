// Node-runnable test for chart axis unit formatting (run with: node --experimental-strip-types src/utils/chartAxis.test.mjs).
import { formatAxisWithUnit } from './chartAxis.ts'

let passed = 0
let failed = 0
function assert(cond, msg) { if (cond) { passed++ } else { failed++; console.error('FAIL:', msg) } }

assert(formatAxisWithUnit(86795, 'pcs') === '86795 pcs', 'count keeps unit')
assert(formatAxisWithUnit(8216389, '元') === '821.64 万元', 'currency scales to 万 with unit')
assert(formatAxisWithUnit(0.12, '%') === '12 %', 'percent shown with %')
assert(formatAxisWithUnit(5, '') === '5', 'no unit → raw')
assert(formatAxisWithUnit(null, 'pcs') === '', 'null → empty')
assert(formatAxisWithUnit(-8216389, '元') === '-821.64 万元', 'negative currency keeps sign')
assert(formatAxisWithUnit('86795', 'pcs') === '86795 pcs', 'string number coerced')

if (failed === 0) { console.log(`chartAxis: ${passed} passed`) } else { console.error(`chartAxis: ${failed} FAILED`); process.exit(1) }
