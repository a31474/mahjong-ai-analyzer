// 用法: node scripts/upstream_botzone_lines.mjs <salasasa-record.json> [roundIndex=1]
//
// 调用 open_mahjong_unity 前端的 salasasa → Botzone 转换（recordConvert/botzoneGuobiao.js），
// 输出指定小局的 Botzone 协议行，供 scripts/compare_botzone_conversion.py 做双跑对比。
//
// 上游仓库位置：默认 <本仓库>/../open_mahjong_unity，可用环境变量 OPEN_MAHJONG_UNITY 覆盖。
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const unityRoot = resolve(process.env.OPEN_MAHJONG_UNITY || join(here, '..', '..', 'open_mahjong_unity'))
const modPath = join(unityRoot, 'open_mahjong_web/client/src/utils/recordConvert/botzoneGuobiao.js')

const recordPath = process.argv[2]
const roundIndex = Number(process.argv[3] || 1)
if (!recordPath) {
  console.error('用法: node scripts/upstream_botzone_lines.mjs <salasasa-record.json> [roundIndex]')
  process.exit(2)
}

let salasasaToBotzone
try {
  ({ salasasaToBotzone } = await import(modPath))
} catch (err) {
  console.error(`无法加载上游转换模块: ${modPath}\n${err.message}`)
  process.exit(3)
}

const src = JSON.parse(readFileSync(recordPath, 'utf8'))
const rec = src.record || src
const input = {
  game_title: { rule: src.rule || 'guobiao', ...(rec.game_title || {}) },
  game_round: rec.game_round,
}
const out = salasasaToBotzone(input)
const game = out.games[roundIndex - 1]
if (!game) {
  console.error(`没有第 ${roundIndex} 局（共 ${out.games.length} 局）`)
  process.exit(4)
}
console.log(game.lines.join('\n'))
