<template>
  <main
    class="mahjongGame replay-page"
    :class="{ 'is-black-tile-face': appearance.tileFaceTheme === 'black' }"
    :style="{ background: appearance.backgroundColorOutside }"
  >
    <div class="replay-layout" :style="{ background: appearance.backgroundColorOutside }">
      <section class="replay-board" :style="{ background: appearance.backgroundColorTable }">
        <div
          ref="stageElement"
          class="game-stage"
          @click.capture="onBoardStep(1)"
          @contextmenu.capture.prevent="onBoardStep(-1)"
          @wheel.capture.prevent="onBoardWheel"
        />

        <div v-if="replay && sceneReady && analysisId" class="ai-panel" aria-label="AI 复盘面板">
          <header class="ai-panel__head">
            <strong>AI 复盘</strong>
            <span v-if="viewerForAi">{{ viewerForAi.username }} 视角</span>
          </header>
          <div v-if="aiLoading" class="ai-panel__state">AI 分析中…</div>
          <div v-else-if="aiError" class="ai-panel__state is-error">{{ aiError }}</div>
          <template v-else-if="aiData && aiData.ai_top && aiData.ai_top.length">
            <ul class="ai-panel__list">
              <li
                v-for="(entry, index) in aiData.ai_top"
                :key="entry.tile"
                :class="{ 'is-best': index === 0 }"
              >
                <span class="ai-panel__tile">
                  <img v-if="aiTileToMmcr(entry.tile) > 0" :src="mmcrTileAsset(aiTileToMmcr(entry.tile))" :alt="aiTileLabel(entry.tile)" />
                  <span v-else class="ai-panel__tile-empty" />
                </span>
                <span class="ai-panel__bar">
                  <i :style="{ width: `${Math.round(entry.prob * 100)}%` }" />
                </span>
                <strong>{{ (entry.prob * 100).toFixed(1) }}%</strong>
              </li>
            </ul>
            <div class="ai-panel__actual" :class="aiData.agree ? 'is-agree' : 'is-disagree'">
              <span>实际打出</span>
              <span class="ai-panel__tile">
                <img v-if="aiTileToMmcr(aiData.actual_tile) > 0" :src="mmcrTileAsset(aiTileToMmcr(aiData.actual_tile))" :alt="aiTileLabel(aiData.actual_tile)" />
                <span v-else class="ai-panel__tile-empty" />
              </span>
              <em>{{ aiData.agree ? '与 AI 一致' : '与 AI 分歧' }}</em>
            </div>
          </template>
          <div v-else class="ai-panel__state">当前步无 AI 分析数据</div>
        </div>

        <div v-if="replay && sceneReady" class="replay-board-tools">
          <button type="button" :class="{ 'is-active': showOtherHands }" @click="toggleOtherHands">
            {{ showOtherHands ? '隐藏他家手牌' : '显示他家手牌' }}
          </button>
          <button type="button" :class="{ 'is-active': playWinAnimation }" @click="playWinAnimation = !playWinAnimation">
            播放和牌动画
          </button>
          <button
            type="button"
            :class="{ 'is-active': chongHintEnabled }"
            title="标红他家待牌；查看牌山时标出摸牌预测"
            @click="toggleChongHint"
          >
            铳张提示
          </button>
          <button type="button" :class="{ 'is-active': showMoqieMode }" @click="toggleMoqieHint">
            显示手摸切
          </button>
          <button type="button" :class="{ 'is-active': wallVisible }" @click="wallVisible = !wallVisible">
            查看牌山
          </button>
          <button type="button" :class="{ 'is-active': scoreboardOpen }" @click="scoreboardOpen = !scoreboardOpen">
            {{ scoreboardOpen ? '关闭计分板' : '打开计分板' }}
          </button>
          <button type="button" :class="{ 'is-active': settingsOpen }" @click="settingsOpen = !settingsOpen">
            游戏设置
          </button>
        </div>

        <div v-if="wallVisible" class="replay-wall-layer">
        <section class="replay-wall" aria-label="当前牌山">
          <header>
            <strong>牌山阅览</strong>
            <span>剩余 {{ remainingWall.length }} 张</span>
            <span v-if="chongHintEnabled" class="replay-wall__legend">
              <i class="is-danger">铳张</i><i class="is-predicted">摸牌预测</i>
            </span>
            <button type="button" @click="wallVisible = false">×</button>
          </header>
          <div class="replay-wall__content">
            <section
              v-for="(hand, seat) in initialHands"
              :key="`initial-hand-${seat}`"
              class="replay-wall__section replay-wall__section--hand"
            >
              <h3>{{ winds[seat] }}家初始手牌</h3>
              <div class="replay-wall__hand-tiles">
                <span v-for="(tile, index) in hand" :key="`${seat}-${index}-${tile}`">
                  <img :src="mmcrTileAsset(tile)" alt="" />
                </span>
              </div>
            </section>
            <section class="replay-wall__section replay-wall__section--wall">
              <h3>牌山</h3>
              <div class="replay-wall__rows">
                <div v-for="row in Math.ceil(wallTilesWithHints.length / 4)" :key="`wall-row-${row}`" class="replay-wall__row">
                  <span
                    v-for="(item, offset) in wallTilesWithHints.slice((row - 1) * 4, row * 4)"
                    :key="`${row}-${offset}-${item.tile}`"
                    :class="{
                      'is-consumed': item.consumed,
                      'is-danger': item.isDanger,
                      'is-predicted': item.isPredicted,
                    }"
                  >
                    <img :src="mmcrTileAsset(item.tile)" alt="" />
                  </span>
                </div>
              </div>
            </section>
          </div>
        </section>
        </div>

        <GameScoreboardPanel
          v-if="scoreboardOpen"
          selectable
          :players="scoreboardPlayers"
          :settlements="scoreboardSettlements"
          :round-label-format="appearance.roundLabelFormat"
          @select-row="jumpToScoreboardRound"
          @close="scoreboardOpen = false"
        />

        <div v-if="settingsOpen" class="replay-settings-layer" @click.self="settingsOpen = false">
          <section class="replay-settings-panel">
            <button type="button" class="replay-settings-panel__close" @click="settingsOpen = false">×</button>
            <SceneAppearancePanel
              :appearance="appearance"
              :background-image-name="backgroundImage?.name ?? null"
              :background-image-loading="backgroundImageLoading"
              :volume="volume"
              @volume="changeVolume"
              @round-label-format="setAppearanceField('roundLabelFormat', $event)"
              @table-color="setAppearanceField('backgroundColorTable', $event)"
              @outside-color="setAppearanceField('backgroundColorOutside', $event)"
              @image-enabled="setAppearanceField('backgroundImageEnabled', $event)"
              @image-alpha="setAppearanceField('backgroundImageAlpha', $event)"
              @image-selected="uploadBackgroundImage"
              @image-cleared="clearBackgroundImage"
              @cover-color="setTileCoverColor"
              @add-cover-color="addTileCoverColor"
              @remove-cover-color="removeTileCoverColor"
              @reorder-cover-colors="reorderTileCoverColors"
              @select-cover-index="selectTileCoverIndex"
              @cover-rotate-mode="setAppearanceField('tileCoverRotateMode', $event)"
              @flower-area-display="setAppearanceField('flowerAreaDisplay', $event)"
              @flower-area-color="setAppearanceField('flowerAreaColor', $event)"
              @flower-area-alpha="setAppearanceField('flowerAreaAlpha', $event)"
              @flower-area-label-color="setAppearanceField('flowerAreaLabelColor', $event)"
              @flower-area-count-color="setAppearanceField('flowerAreaCountColor', $event)"
              @flower-area-label-scale="setAppearanceField('flowerAreaLabelScale', $event)"
              @tile-face-theme="setAppearanceField('tileFaceTheme', $event)"
              @flower-face-theme="setAppearanceField('flowerFaceTheme', $event)"
              @font-theme="setAppearanceField('fontTheme', $event)"
              @latin-font-theme="setAppearanceField('latinFontTheme', $event)"
              @reset="resetAppearance"
            />
          </section>
        </div>

        <div
          v-if="resultPanelVisible && roundResult"
          class="end-result-layer replay-end-result"
          :class="{ 'is-instant-fans': !playWinAnimation }"
        >
          <section
            v-if="roundResult.kind === 'draw'"
            class="end-result-panel end-result-panel--draw"
            aria-label="本局流局"
          >
            <div
              v-for="seat in resultPlayers"
              :key="`draw-${seat.seat}`"
              class="end-result-draw-delta"
              :class="`is-rel-${seat.relative}`"
            >
              <span class="end-result-draw-delta__name">{{ seat.player }}</span>
              <span
                class="end-result-draw-delta__change"
                :class="seat.value > 0 ? 'is-plus' : seat.value < 0 ? 'is-minus' : 'is-zero'"
              >
                {{ seat.value > 0 ? '+' : '' }}{{ seat.value }}
              </span>
            </div>
            <div class="end-result-draw-title">流局</div>
            <button type="button" class="end-result-ready-button" @click="finishTerminalResult">确定</button>
          </section>

          <section v-else class="end-result-panel end-result-panel--win" aria-label="本局和牌结算">
            <div v-if="resultClosedTiles.length || resultWinTile" class="end-result-hand">
              <span v-for="(tile, index) in resultClosedTiles" :key="`closed-${index}`" class="end-result-tile">
                <img :src="mmcrTileAsset(tile)" alt="" />
              </span>
              <span v-if="resultMeldTiles.length" class="end-result-hand__split" />
              <span v-for="(tile, index) in resultMeldTiles" :key="`meld-${index}`" class="end-result-tile">
                <img :src="mmcrTileAsset(tile)" alt="" />
              </span>
              <span class="end-result-hand__split" />
              <span v-if="resultWinTile" class="end-result-tile is-winning">
                <img :src="mmcrTileAsset(resultWinTile)" alt="和牌张" />
              </span>
            </div>
            <div v-if="resultFlowerTiles.length" class="end-result-flowers">
              <span class="end-result-flowers__label">花</span>
              <span v-for="(tile, index) in resultFlowerTiles" :key="`flower-${index}`" class="end-result-tile end-result-tile--flower">
                <img :src="mmcrTileAsset(tile)" alt="" />
              </span>
            </div>
            <div class="end-result-fan-grid" :style="{ minHeight: fanGridMinHeight }">
              <div
                v-for="(fan, index) in resultFans"
                :key="`${fan.name}-${index}`"
                class="end-result-fan"
                :class="{ 'is-visible': index < revealedFanCount }"
                :style="{ '--fan-name-size': `${fanNameFontSize(fan.name)}px` }"
              >
                <span>{{ fan.name }}</span>
                <strong>{{ fan.value }}</strong>
              </div>
            </div>
            <div class="end-result-total" :class="{ 'is-visible': showResultTotal }">
              <div class="end-result-total__line">
                <span class="end-result-total__method">{{ winMethodLabel }}</span>
                <strong>{{ roundResult.fan }}</strong><span>番</span>
              </div>
            </div>
            <div class="end-result-diamond">
              <article
                v-for="slot in diamondSlots"
                :key="`result-seat-${slot.relative}`"
                class="end-result-seat"
                :class="[`is-rel-${slot.relative}`, { 'is-winner': slot.seat === roundResult.winnerSeat }]"
              >
                <strong class="end-result-seat__name">{{ slot.player }}</strong>
                <div class="end-result-seat__score">
                  <span>{{ slot.score }}</span>
                  <span :class="slot.value > 0 ? 'is-plus' : slot.value < 0 ? 'is-minus' : 'is-zero'">
                    {{ slot.value > 0 ? '+' : '' }}{{ slot.value }}
                  </span>
                </div>
              </article>
            </div>
            <button v-if="showResultConfirm" type="button" class="end-result-ready-button" @click="finishTerminalResult">
              确定
            </button>
          </section>
        </div>

        <div v-if="loading || errorMessage" class="replay-state">
          <div class="replay-state__card">
            <strong>{{ errorMessage ? '无法打开牌谱' : '正在读取牌谱' }}</strong>
            <span>{{ errorMessage || '正在重建 2D 牌桌…' }}</span>
            <button v-if="errorMessage" type="button" @click="showInputPage">返回输入页</button>
          </div>
        </div>

        <div v-if="inputPage && !replay && !loading && !errorMessage" class="replay-input-layer">
          <section class="replay-input-panel">
            <h2>加载牌谱进行 AI 复盘</h2>
            <label class="replay-input__field">
              <span>对局 ID（后端从平台拉取）</span>
              <input v-model="gameIdInput" type="text" placeholder="对局 ID 或回放链接（如 nfkKiKHWH4 / https://salasasa.cn/2d/record/nfkKiKHWH4）" @keydown.enter="submitInput" />
            </label>
            <label class="replay-input__field">
              <span>平台地址（可选）</span>
              <input v-model="platformInput" type="text" placeholder="https://salasasa.cn" @keydown.enter="submitInput" />
            </label>
            <div class="replay-input__or">—— 或直接粘贴牌谱 JSON（上传模式）——</div>
            <label class="replay-input__field">
              <span>牌谱 JSON</span>
              <textarea
                v-model="recordJsonInput"
                rows="6"
                placeholder='{"game_id": "...", "rule": "guobiao", "record": {"game_round": {...}}}'
              />
            </label>
            <button type="button" class="replay-input__submit" :disabled="preparing" @click="submitInput">
              {{ preparing ? '分析中…' : '开始分析' }}
            </button>
            <p v-if="inputError" class="replay-input__error">{{ inputError }}</p>
          </section>
        </div>

        <div v-if="replay && sceneReady" class="replay-controls" aria-label="牌谱播放控制">
          <div class="replay-controls__row">
            <button type="button" title="上一局" :disabled="terminalLocked" @click="changeRound(-1)">«</button>
            <button type="button" title="上一步" :disabled="terminalLocked" @click="step(-1)">‹</button>
            <button type="button" class="is-play" :disabled="terminalLocked" @click="togglePlaying">{{ playing ? '暂停' : '播放' }}</button>
            <button type="button" title="下一步" :disabled="terminalLocked" @click="step(1)">›</button>
            <button type="button" title="下一局" :disabled="terminalLocked" @click="changeRound(1)">»</button>
            <label class="replay-controls__select">
              <span>局</span>
              <select :value="roundIndex" :disabled="terminalLocked" @change="selectRound(Number(($event.target as HTMLSelectElement).value))">
                <option v-for="(round, index) in replay.rounds" :key="`round-select-${index}`" :value="index">
                  {{ roundSelectLabel(round, index) }}
                </option>
              </select>
            </label>
            <label class="replay-controls__select">
              <span>巡目</span>
              <select :value="xunmuSelectValue" :disabled="terminalLocked" @change="selectXunmu(($event.target as HTMLSelectElement).value)">
                <option v-for="(_, index) in currentXunmuNodes" :key="`xunmu-${index}`" :value="String(index)">
                  {{ index }}巡
                </option>
                <option v-if="currentXunmuNodes.at(-1) !== maxNode" value="end">本局终点</option>
              </select>
            </label>
            <span class="replay-controls__status">
              {{ actionLabel }} · {{ node }}/{{ maxNode }}
            </span>
          </div>
          <input
            v-model.number="node"
            class="replay-controls__range"
            type="range"
            min="0"
            :max="maxNode"
            step="1"
            :disabled="terminalLocked"
            aria-label="牌谱节点"
          />
        </div>
      </section>

      <aside class="replay-sidebar">
        <header class="replay-header">
          <div>
            <p class="replay-header__eyebrow">SALASASA 2D 牌谱</p>
            <h1>{{ detail?.game_id || route.params.gameId }}</h1>
          </div>
          <button type="button" class="replay-icon-button" title="加载新牌谱" @click="showInputPage">×</button>
        </header>

        <div v-if="!localRecord" class="replay-share">
          <div class="replay-share__split">
            <button type="button" class="replay-primary-button replay-primary-button--2d" @click="copyShareLink('2d')">
              {{ copiedKind === '2d' ? '链接已复制' : '复制分享链接' }}
            </button>
            <div class="replay-share__row">
              <button
                type="button"
                class="replay-primary-button replay-primary-button--node"
                title="复制当前局数与节点位置链接"
                @click="copyShareLink('node')"
              >
                {{ copiedKind === 'node' ? '已复制' : '复制当前node' }}
              </button>
              <button type="button" class="replay-primary-button replay-primary-button--3d" @click="copyShareLink('3d')">
                {{ copiedKind === '3d' ? '已复制' : '复制 3D' }}
              </button>
            </div>
          </div>
        </div>

        <section v-if="replay" class="replay-section">
          <h2>选择小局</h2>
          <div class="replay-rounds">
            <button
              v-for="(_, index) in replay.rounds"
              :key="index"
              type="button"
              :disabled="terminalLocked"
              :class="[{ 'is-active': roundIndex === index }, roundOutcomeClass(index)]"
              @mouseenter="moveRoundTooltip(index, $event)"
              @mousemove="moveRoundTooltip(index, $event)"
              @mouseleave="hoveredRoundIndex = null"
              @focus="showRoundTooltipFromFocus(index, $event)"
              @blur="hoveredRoundIndex = null"
              @click="selectRound(index)"
            >
              {{ index + 1 }}
            </button>
          </div>
          <div
            v-if="hoveredRoundIndex != null"
            class="replay-round-tooltip"
            :style="{ left: `${roundTooltipPosition.x}px`, top: `${roundTooltipPosition.y}px` }"
          >
            <strong>第 {{ hoveredRoundIndex + 1 }} 局分数变动</strong>
            <span
              v-for="row in roundScoreChangeRows(hoveredRoundIndex)"
              :key="`${hoveredRoundIndex}-${row.original}`"
              :class="{ 'is-viewer': row.original === viewerOriginal }"
            >
              <em>{{ row.username }}</em>
              <b :class="{ 'is-plus': row.change > 0, 'is-minus': row.change < 0 }">
                {{ row.change > 0 ? '+' : '' }}{{ row.change }}
              </b>
            </span>
          </div>
        </section>

        <section v-if="replay" class="replay-section">
          <h2>查看视角</h2>
          <div class="replay-viewpoints">
            <button
              v-for="player in viewpointPlayers"
              :key="player.original"
              type="button"
              :class="{ 'is-active': viewerOriginal === player.original }"
              @click="viewerOriginal = player.original"
            >
              <span>{{ player.wind }}</span>
              <strong>{{ player.username }}</strong>
              <small>{{ player.score }}</small>
            </button>
          </div>
        </section>

        <section v-if="detail" class="replay-section replay-meta">
          <h2>对局信息</h2>
          <div ref="gameInfoScrollElement" class="replay-meta__scroll" @wheel.prevent="onGameInfoWheel">
            <dl>
              <div v-for="row in gameInfoRows" :key="row.label">
                <dt>{{ row.label }}</dt>
                <dd :class="{ 'is-code': row.code }">{{ row.value }}</dd>
              </div>
            </dl>
          </div>
        </section>

        <p class="replay-keyboard">鼠标左键下一步、右键上一步，滚轮切换巡目；键盘 ←/→ 步进，Shift + ←/→ 切换小局，空格播放或暂停。</p>
      </aside>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MahjongScene } from '@/game2d/game/scene/MahjongScene'
import { GAME_SOUND_ASSETS, getPreloadedSoundUrl } from '@/game2d/game/resources'
import { playerProfileUrl, publicApiGet, publicRecordUrl } from '@/game2d/salasasa/api'
import { RecordReplay, type PublicGameRecord, type RecordRound, type RecordTick } from '@/game2d/replay/recordReplay'
import { isLocalReplayRecord, loadLocalReplayRecord } from '@/game2d/replay/localReplayRecord'
import {
  AiApiError,
  fetchStep,
  prepareAnalysis,
  type AiStepResult,
  type PrepareResult,
} from '@/game2d/ai/api'
import {
  loadStoredSceneAppearance,
  loadStoredVolume,
  resetStoredSceneAppearance,
  saveStoredSceneAppearance,
  saveStoredVolume,
} from '@/game2d/lib/storage'
import {
  clearStoredSceneBackgroundImage,
  loadStoredSceneBackgroundImage,
  saveStoredSceneBackgroundImage,
} from '@/game2d/lib/sceneBackgroundImage'
import {
  DEFAULT_SCENE_APPEARANCE,
  MAX_TILE_COVER_COLORS,
  normalizeSceneAppearanceSettings,
} from '@/game2d/lib/sceneAppearance'
import { tingpaiCheck } from '@/game2d/calc/guobiao'
import { buildLocalWaitData } from '@/game2d/calc/guobiao/waitTips'
import { mmcrTileToSalasasa, salasasaTileToMmcr } from '@/game2d/salasasa/gameAdapter'
import { formatFanField, resolveFanLabel } from '@/constants/guessFanCatalog'
import { formatFanCount, translateFanName } from '@/i18n/fanNames'
import { locale, roundLabelKey, tr } from '@/i18n'
import {
  mmcrSettlementSortKey,
  splitSettlementHand,
} from '@/game2d/lib/settlementHand'
import type { ActiveSessionSnapshot, MeldSnapshot } from '@/game2d/game/scene/types'
import GameScoreboardPanel from './GameScoreboardPanel.vue'
import SceneAppearancePanel from './SceneAppearancePanel.vue'

const route = useRoute()
const router = useRouter()
const stageElement = ref<HTMLElement | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const detail = ref<PublicGameRecord | null>(null)
const replay = ref<RecordReplay | null>(null)
const roundIndex = ref(0)
const node = ref(0)
const viewerOriginal = ref(0)
const actionLabel = ref('局初')
const playing = ref(false)
const sceneReady = ref(false)
const copiedKind = ref<'2d' | '3d' | 'node' | null>(null)
const localRecord = computed(() => isLocalReplayRecord(route.params.gameId))
const currentScores = ref<number[]>([])
const showOtherHands = ref(true)
const playWinAnimation = ref(false)
const chongHintEnabled = ref(true)
const showMoqieMode = ref(true)
const gameInfoScrollElement = ref<HTMLElement | null>(null)
const wallVisible = ref(false)
const resultPanelVisible = ref(false)
const revealedFanCount = ref(0)
const showResultTotal = ref(false)
const showResultConfirm = ref(false)
const terminalLocked = ref(false)
const scoreboardOpen = ref(false)
const settingsOpen = ref(false)
const hoveredRoundIndex = ref<number | null>(null)
const roundTooltipPosition = ref({ x: 0, y: 0 })
const currentRanks = ref<Record<string, string>>({})
const backgroundImage = ref<Awaited<ReturnType<typeof loadStoredSceneBackgroundImage>>>(null)
const backgroundImageLoading = ref(true)
const appearance = ref(loadStoredSceneAppearance())
const volume = ref(loadStoredVolume())
const analysisId = ref<string | null>(null)
const aiData = ref<AiStepResult | null>(null)
const aiLoading = ref(false)
const aiError = ref('')
const inputPage = ref(false)
const gameIdInput = ref('')
const platformInput = ref('')
const recordJsonInput = ref('')
const inputError = ref('')
const preparing = ref(false)
let aiNodeMaps: Map<number, Map<number, Map<number, number>>> | null = null
let aiRequestId = 0
let scene: MahjongScene | null = null
let playTimer: number | null = null
let skipNextPositionRender = false
let resultTimers: number[] = []
let activeTerminalKey = ''

const maxNode = computed(() => replay.value?.rounds[roundIndex.value]?.action_ticks?.length ?? 0)
const currentRound = computed(() => replay.value?.rounds[roundIndex.value])
const winds = ['东', '南', '西', '北']
const viewpointPlayers = computed(() => {
  if (!replay.value || !currentRound.value) return []
  return [0, 1, 2, 3].map((original) => {
    const seat = replay.value!.rounds[roundIndex.value].seats?.[original] ?? original
    const player = replay.value!.playerForSeat(currentRound.value!, seat)
    return {
      original,
      wind: winds[seat] || String(seat + 1),
      username: player?.username || `玩家 ${original + 1}`,
      score: currentScores.value[original] ?? player?.score ?? 0,
    }
  })
})

const formattedCreatedAt = computed(() => {
  if (!detail.value?.created_at) return '—'
  const date = new Date(detail.value.created_at)
  return Number.isNaN(date.getTime()) ? detail.value.created_at : date.toLocaleString('zh-CN', { hour12: false })
})

const roomLabel = computed(() => {
  if (detail.value?.room_type === 'match') return '匹配房间'
  if (detail.value?.room_type === 'events') return '赛事房间'
  return '自定义房间'
})

interface GameInfoRow {
  label: string
  value: string
  code?: boolean
}

function hasGameTitleField(title: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(title, key) && title[key] != null
}

function enabledLabel(value: unknown): string {
  if (value === true || value === 1 || String(value).toLowerCase() === 'true') return '开启'
  return '关闭'
}

function compactRecordTime(value: unknown): string {
  const text = String(value ?? '').trim()
  if (!text) return '—'
  return text.replace('T', ' ').replace(/(\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/, '')
}

function ruleDisplayName(rule: unknown): string {
  const names: Record<string, string> = {
    guobiao: '国标麻将',
    riichi: '立直麻将',
    classical: '古典麻将',
    qingque: '青雀麻将',
    sichuan: '四川麻将',
    changsha: '长沙麻将',
    taiwan: '台湾麻将',
  }
  const key = String(rule ?? '').toLowerCase()
  return names[key] || String(rule || '—')
}

function subRuleDisplayName(subRule: unknown): string {
  const names: Record<string, string> = {
    'guobiao/standard': '国标标准',
  }
  const key = String(subRule ?? '')
  return names[key] || key || '—'
}

function roundModeLabel(maxRound: unknown, queueType: unknown): string {
  const queue = String(queueType ?? '').toLowerCase()
  if (queue.endsWith('_dongfeng')) return '东风'
  if (queue.endsWith('_banzhuang')) return '半庄'
  if (queue.endsWith('_quanzhuang')) return '全庄'
  const count = Number(maxRound)
  if (count === 1) return '东风'
  if (count === 2) return '半庄'
  if (count === 4) return '全庄'
  return Number.isFinite(count) && count > 0 ? `${count} 圈` : '—'
}

function matchTierLabel(value: unknown): string {
  const labels: Record<string, string> = {
    beginner: '初级场',
    intermediate: '中级场',
    advanced: '高级场',
    mcrpl: 'MCRPL',
  }
  const key = String(value ?? '').toLowerCase()
  return labels[key] || String(value || '—')
}

const gameInfoRows = computed<GameInfoRow[]>(() => {
  const title = detail.value?.record?.game_title || {}
  const rows: GameInfoRow[] = []
  const push = (label: string, value: unknown, code = false) => {
    const text = String(value ?? '').trim()
    if (text) rows.push({ label, value: text, code })
  }
  const queueType = title.match_queue_type
  const queueTier = String(queueType ?? '').split('_')[0]

  push('规则', ruleDisplayName(title.rule ?? detail.value?.rule))
  push('房间', roomLabel.value)
  push('完成时间', hasGameTitleField(title, 'end_time') ? compactRecordTime(title.end_time) : formattedCreatedAt.value)
  if (hasGameTitleField(title, 'sub_rule') || detail.value?.sub_rule) {
    push('子规则', subRuleDisplayName(title.sub_rule ?? detail.value?.sub_rule))
  }
  if (detail.value?.match_type) {
    push('对局类型', String(detail.value.match_type).includes('rank') ? '排位对局' : detail.value.match_type)
  }
  if (hasGameTitleField(title, 'match_tier') || queueTier) {
    push('场次', matchTierLabel(title.match_tier ?? queueTier))
  }
  if (hasGameTitleField(title, 'max_round') || queueType) {
    push('局制', roundModeLabel(title.max_round, queueType))
  }
  if (hasGameTitleField(title, 'hepai_limit')) push('起和番', `${Number(title.hepai_limit) || 0} 番`)
  if (hasGameTitleField(title, 'round_timer')) push('局时', `${Number(title.round_timer) || 0} 秒`)
  if (hasGameTitleField(title, 'step_timer')) push('步时', `${Number(title.step_timer) || 0} 秒`)
  if (hasGameTitleField(title, 'open_cuohe')) push('错和', enabledLabel(title.open_cuohe))
  if (hasGameTitleField(title, 'tips')) push('对局提示', enabledLabel(title.tips))
  if (hasGameTitleField(title, 'allow_spectator')) push('允许观战', enabledLabel(title.allow_spectator))
  if (hasGameTitleField(title, 'tactical_call')) push('战术鸣牌', enabledLabel(title.tactical_call))
  if (hasGameTitleField(title, 'claim_protection')) push('鸣牌保护', enabledLabel(title.claim_protection))
  if (hasGameTitleField(title, 'is_player_set_random_seed')) {
    push('复式', enabledLabel(title.is_player_set_random_seed))
  }
  if (hasGameTitleField(title, 'start_time')) push('开始时间', compactRecordTime(title.start_time))

  const entryOrder = Array.isArray(title.player_entry_order) ? title.player_entry_order : []
  if (entryOrder.length) {
    const usernames = entryOrder.map((userId) => {
      const player = detail.value?.players.find((item) => Number(item.user_id) === Number(userId))
      return player?.username || String(userId)
    })
    push('入场顺序', usernames.join(' → '))
  }
  for (let index = 0; index < 4; index += 1) {
    const name = title[`p${index}_name`]
    const userId = title[`p${index}_uid`]
    if (name != null || userId != null) {
      push(`玩家 ${index}`, `${name || '—'}${userId != null ? ` · ID ${userId}` : ''}`)
    }
  }
  if (hasGameTitleField(title, 'commitment_hex')) push('承诺值', title.commitment_hex, true)
  if (hasGameTitleField(title, 'salt')) push('盐值', title.salt, true)
  if (hasGameTitleField(title, 'master_seed_hex')) push('主种子', title.master_seed_hex, true)
  return rows
})

/**
 * 错和 tick：fan 列表包含「错和」的 hu_* 动作。服务端记录格式中错和无 end、
 * 对局继续，因此它只是普通节点，不能被当作本局终点（真正的和牌/流局在其后）。
 */
function isCuoheTick(tick: RecordTick | undefined): boolean {
  if (!tick?.length) return false
  const action = String(tick[0] ?? '')
  if (!action.startsWith('hu_')) return false
  return Array.isArray(tick[3]) && tick[3].includes('错和')
}

const roundResult = computed(() => {
  const round = currentRound.value
  if (!round || node.value <= 0) return null
  const ticks = (round.action_ticks || []).slice(0, node.value)
  const tick = [...ticks].reverse().find((item) => {
    if (isCuoheTick(item)) return false
    const action = String(item?.[0] ?? '')
    return action.startsWith('hu_') || action === 'liuju' || action === 'ryuukyoku'
  })
  if (!tick) return null
  const action = String(tick[0] ?? '')
  const scoreValues = action === 'ryuukyoku' || action === 'liuju' ? tick[2] : tick[4]
  const changes = Array.isArray(scoreValues)
    ? scoreValues.slice(0, 4).map((value, seat) => ({
      seat,
      player: replay.value?.playerForSeat(round, seat)?.username || `玩家 ${seat + 1}`,
      value: Number(value) || 0,
    }))
    : []
  if (!action.startsWith('hu_')) return { kind: 'draw' as const, changes, tick, action }
  const winnerSeat = Number(tick[1]) || 0
  return {
    kind: 'win' as const,
    player: replay.value?.playerForSeat(round, winnerSeat)?.username || `玩家 ${winnerSeat + 1}`,
    fan: Number(tick[2]) || 0,
    fans: Array.isArray(tick[3]) ? tick[3].map(String) : [],
    changes,
    tick,
    action,
    winnerSeat,
  }
})

const resultPosition = computed(() => (
  replay.value ? replay.value.build(roundIndex.value, node.value, viewerOriginal.value, true) : null
))
const resultWinner = computed(() => {
  if (roundResult.value?.kind !== 'win') return null
  return resultPosition.value?.snapshot.seats.find((seat) => seat.seat_index === roundResult.value!.winnerSeat) ?? null
})
const resultWinTile = computed(() => {
  if (roundResult.value?.kind !== 'win') return 0
  const fromTick = Number(roundResult.value.tick[5])
  if (fromTick > 0) return salasasaTileToMmcr(fromTick)
  return resultWinner.value?.drawn_tile ?? 0
})
const resultClosedTiles = computed(() => {
  const tiles = [...(resultWinner.value?.hand_tiles ?? [])]
  if (resultWinner.value?.drawn_tile != null) tiles.push(resultWinner.value.drawn_tile)
  return splitSettlementHand(
    tiles,
    resultWinTile.value,
    resultWinner.value?.melds.length ?? 0,
    mmcrSettlementSortKey,
  )
})
function expandResultMeld(meld: MeldSnapshot): number[] {
  if (meld.type === 'sequence') return [meld.tile - 1, meld.tile, meld.tile + 1]
  return Array(meld.type === 'kong' ? 4 : 3).fill(meld.tile)
}
const resultMeldTiles = computed(() => (resultWinner.value?.melds ?? []).flatMap(expandResultMeld))
const resultFlowerTiles = computed(() => resultWinner.value?.flower_tiles ?? [])
const resultFans = computed(() => roundResult.value?.kind === 'win'
  ? roundResult.value.fans.map((name) => {
    const { definition, totalValue } = resolveFanLabel(name, ['guobiao'])
    const value = definition
      ? `${totalValue ?? formatFanField(definition.fan)}番`
      : ''
    return {
      name: translateFanName(name),
      value: value ? formatFanCount(value.replace(/番$/, '')) : '',
    }
  })
  : [])
function fanNameFontSize(value: string): number {
  const units = Array.from(String(value || '')).reduce(
    (total, character) => total + (/^[\x00-\xff]$/.test(character) ? 0.55 : 1),
    0,
  )
  if (units <= 7) return 20
  return Math.max(12, Math.round((20 * 7 / units) * 10) / 10)
}
const winMethodLabel = computed(() => roundResult.value?.kind === 'win' && roundResult.value.action === 'hu_self'
  ? tr('自摸')
  : tr('点和'))
const fanGridMinHeight = computed(() => `${Math.max(1, Math.ceil((resultFans.value.length || 1) / 2)) * 36}px`)
const resultPlayers = computed(() => {
  const round = currentRound.value
  const snapshot = resultPosition.value?.snapshot
  if (!round || !snapshot) return []
  const viewerSeat = round.seats?.[viewerOriginal.value] ?? viewerOriginal.value
  const changes = new Map((roundResult.value?.changes ?? []).map((change) => [change.seat, change.value]))
  return snapshot.seats.map((seat) => ({
    seat: seat.seat_index,
    relative: (seat.seat_index - viewerSeat + 4) % 4,
    player: seat.username || `玩家 ${seat.seat_index + 1}`,
    score: seat.score,
    value: changes.get(seat.seat_index) ?? 0,
  }))
})
const diamondSlots = computed(() => {
  const byRelative = new Map(resultPlayers.value.map((item) => [item.relative, item]))
  return [2, 3, 1, 0].map((relative) => byRelative.get(relative) ?? {
    seat: -1, relative, player: '—', score: 0, value: 0,
  })
})
const remainingWall = computed(() => replay.value?.remainingWallAt(roundIndex.value, node.value) ?? [])
const wallTiles = computed(() => replay.value?.wallViewAt(roundIndex.value, node.value) ?? [])
const replayDangerBySeat = computed(() => {
  const snapshot = resultPosition.value?.snapshot
  const dangerBySeat = new Map<number, Set<number>>()
  if (!snapshot || !chongHintEnabled.value) return dangerBySeat

  const waitsBySeat = new Map<number, Set<number>>()
  for (const seat of snapshot.seats) {
    waitsBySeat.set(seat.seat_index, waitingTilesForSnapshotSeat(seat))
  }

  const hiddenSeat = waitingForDrawAfterCut(snapshot) ? Number(snapshot.state.last_actor) : -1
  for (const seat of snapshot.seats) {
    const danger = new Set<number>()
    if (seat.seat_index !== hiddenSeat) {
      for (const [otherSeat, waits] of waitsBySeat) {
        if (otherSeat === seat.seat_index) continue
        for (const tile of waits) danger.add(tile)
      }
    }
    dangerBySeat.set(seat.seat_index, danger)
  }
  return dangerBySeat
})
const predictedWallIndices = computed(() => {
  const snapshot = resultPosition.value?.snapshot
  const tiles = wallTiles.value
  const predicted = new Set<number>()
  if (!snapshot || !chongHintEnabled.value || tiles.length === 0) return predicted

  let front = 0
  while (front < tiles.length && tiles[front].consumed) front += 1
  const currentPlayer = Number(snapshot.state.current_player)
  const anchor = waitingForDrawAfterCut(snapshot)
    ? Number(snapshot.state.last_actor)
    : currentPlayer
  const viewerSeat = Number(snapshot.viewer.seat_index)
  const offset = (viewerSeat - anchor + 4) % 4

  for (let n = 0; n < 6; n += 1) {
    const index = front + offset + n * 4 - 1
    if (index < front) continue
    if (index >= tiles.length) break
    if (!tiles[index].consumed) predicted.add(index)
  }
  return predicted
})
const wallTilesWithHints = computed(() => {
  const dangerTiles = new Set<number>()
  for (const waits of replayDangerBySeat.value.values()) {
    for (const tile of waits) dangerTiles.add(tile)
  }
  return wallTiles.value.map((item, index) => ({
    ...item,
    isDanger: chongHintEnabled.value && dangerTiles.has(item.tile),
    isPredicted: chongHintEnabled.value && predictedWallIndices.value.has(index),
  }))
})
const initialHands = computed(() => replay.value?.initialHandsAt(roundIndex.value) ?? [])
const currentXunmuNodes = computed(() => replay.value?.xunmuNodes(roundIndex.value, viewerOriginal.value) ?? [0])
const currentXunmu = computed(() => {
  let index = 0
  currentXunmuNodes.value.forEach((target, targetIndex) => {
    if (target <= node.value) index = targetIndex
  })
  return index
})
const xunmuSelectValue = computed(() => (
  node.value === maxNode.value && currentXunmuNodes.value.at(-1) !== maxNode.value
    ? 'end'
    : String(currentXunmu.value)
))
const viewerForAi = computed(() => (
  viewpointPlayers.value.find((player) => player.original === viewerOriginal.value) ?? null
))
/**
 * 后端 meta 节点 step 是「决策 tick」（摸牌/鸣牌 tick），本家打牌 tick 是其后的
 * 第一个 'c'。aiNodeMaps 建立 打牌tick → 后端step 映射，只有当前 tick 命中
 * 打牌节点时才发起 AI 请求。
 */
const aiStepForCurrentTick = computed<number | null>(() => {
  if (!analysisId.value || !replay.value || !currentRound.value) return null
  const tick = currentRound.value.action_ticks?.[node.value]
  if (!tick || String(tick[0] ?? '') !== 'c') return null
  return aiNodeMaps?.get(roundIndex.value)?.get(viewerOriginal.value)?.get(node.value) ?? null
})
const scoreboardPlayers = computed(() => {
  if (!replay.value || !detail.value) return []
  return [0, 1, 2, 3].map((original) => {
    const player = detail.value!.players.find((item) => item.original_player_index === original)
      || detail.value!.players[original]
    return {
      player_index: original,
      original_player_index: original,
      user_id: player?.user_id ?? 0,
      username: player?.username ?? `玩家 ${original + 1}`,
      score: Number(player?.score ?? 0),
      score_history: replay.value!.rounds.map((_, index) => {
        const value = replay.value!.roundScoreChangesByOriginal(index)[original] ?? 0
        return value > 0 ? `+${value}` : String(value)
      }),
      round_number_history: replay.value!.rounds.map((round, index) => (
        Number(round.current_round ?? index + 1)
      )),
    }
  })
})
const scoreboardSettlements = computed(() => replay.value?.rounds.map((round) => {
  const terminal = terminalTick(round)
  if (!terminal) return '—'
  const action = String(terminal[0] ?? '')
  if (action === 'liuju' || action === 'ryuukyoku') return '流局'
  const fans = Array.isArray(terminal[3]) ? terminal[3].map(String) : []
  const mainFan = fans.find((fan) => !fan.startsWith('花牌')) || fans[0]
  return mainFan || `${Number(terminal[2]) || 0}番`
}) ?? [])

function stopPlaying() {
  playing.value = false
  if (playTimer != null) window.clearInterval(playTimer)
  playTimer = null
}

function startPlaying() {
  if (!replay.value || terminalLocked.value) return
  stopPlaying()
  playing.value = true
  playTimer = window.setInterval(() => {
    if (node.value < maxNode.value) {
      advanceAnimatedStep()
    } else if (roundIndex.value < replay.value!.rounds.length - 1) {
      roundIndex.value += 1
      node.value = 0
    } else {
      stopPlaying()
    }
  }, 700)
}

function togglePlaying() {
  if (playing.value) stopPlaying()
  else startPlaying()
}

function clearResultTimers() {
  for (const timer of resultTimers) window.clearTimeout(timer)
  resultTimers = []
}

function resetTerminalPresentation() {
  clearResultTimers()
  resultPanelVisible.value = false
  terminalLocked.value = false
  activeTerminalKey = ''
}

function scheduleResult(callback: () => void, delay: number) {
  resultTimers.push(window.setTimeout(callback, delay))
}

function finishTerminalResult() {
  if (!terminalLocked.value) return
  const nextRound = roundIndex.value + 1
  resetTerminalPresentation()
  if (replay.value && nextRound < replay.value.rounds.length) {
    roundIndex.value = nextRound
    node.value = 0
  }
}

function revealReplayWinHand(audible: boolean) {
  if (!scene || !replay.value || !currentRound.value) return
  const ticks = currentRound.value.action_ticks || []
  let terminalIndex = Math.min(node.value - 1, ticks.length - 1)
  while (terminalIndex >= 0) {
    const terminalAction = String(ticks[terminalIndex]?.[0] ?? '')
    if (terminalAction.startsWith('hu_')) break
    terminalIndex -= 1
  }
  if (terminalIndex < 0) return
  const update = replay.value.eventForStep(
    roundIndex.value,
    terminalIndex,
    viewerOriginal.value,
    showOtherHands.value,
  )
  if (!update) return
  decorateEventRanks(update)
  update.event = { ...update.event, silent: !audible }
  scene.handleEvent(update)
}

function presentTerminalResult(action: string, handRevealApplied = false) {
  const terminalKey = `${roundIndex.value}:${node.value}:${action}`
  if (terminalLocked.value && activeTerminalKey === terminalKey) return
  activeTerminalKey = terminalKey
  terminalLocked.value = true
  stopPlaying()
  clearResultTimers()
  if (action === 'liuju' || action === 'ryuukyoku') {
    resultPanelVisible.value = true
    revealedFanCount.value = 0
    showResultTotal.value = false
    showResultConfirm.value = true
    scheduleResult(finishTerminalResult, 3500)
    return
  }
  if (!action.startsWith('hu_')) {
    resetTerminalPresentation()
    return
  }
  // The table win action is independent from the settlement-panel animation:
  // always reveal the winner's hand and play the final win sound.
  if (!handRevealApplied) revealReplayWinHand(true)
  if (!playWinAnimation.value) {
    revealedFanCount.value = resultFans.value.length
    showResultTotal.value = true
    showResultConfirm.value = true
    // Keep the same table-side "和" / voice / hand-reveal presentation time.
    // Only the fan rows themselves skip their staggered entrance.
    scheduleResult(() => {
      resultPanelVisible.value = true
    }, 1500)
    return
  }
  revealedFanCount.value = 0
  showResultTotal.value = false
  showResultConfirm.value = false
  scheduleResult(() => {
    resultPanelVisible.value = true
    resultFans.value.forEach((_, index) => {
      scheduleResult(() => {
        revealedFanCount.value = index + 1
        scene?.playUiSound('fan-reveal')
      }, index * 500)
    })
    scheduleResult(() => {
      showResultTotal.value = true
      showResultConfirm.value = true
      if (roundResult.value?.kind === 'win') scene?.playResultGong(roundResult.value.fans)
    }, resultFans.value.length * 500 + 350)
  }, 1500)
}

function step(delta: number) {
  if (terminalLocked.value) return
  stopPlaying()
  resetTerminalPresentation()
  if (delta > 0 && node.value < maxNode.value) {
    advanceAnimatedStep()
    return
  }
  const next = node.value + delta
  if (next >= 0 && next <= maxNode.value) {
    node.value = next
  } else if (next < 0 && roundIndex.value > 0) {
    roundIndex.value -= 1
    node.value = roundBackTargetNode(roundIndex.value)
  } else if (next > maxNode.value && replay.value && roundIndex.value < replay.value.rounds.length - 1) {
    roundIndex.value += 1
    node.value = 0
  }
}

function roundBackTargetNode(index: number): number {
  const ticks = replay.value?.rounds[index]?.action_ticks ?? []
  const terminalIndex = ticks.findIndex((tick) => {
    if (isCuoheTick(tick)) return false
    const action = String(tick?.[0] ?? '')
    return action.startsWith('hu_') || action === 'liuju' || action === 'ryuukyoku'
  })
  // node is the number of ticks already applied, so the terminal tick's index
  // is exactly the stable position immediately before its presentation starts.
  return terminalIndex >= 0 ? terminalIndex : ticks.length
}

function advanceAnimatedStep() {
  if (!scene || !replay.value || node.value >= maxNode.value) return
  const nextNode = node.value + 1
  const tick = currentRound.value?.action_ticks?.[node.value]
  const action = String(tick?.[0] ?? '')
  const rawUpdate = replay.value.eventForStep(
    roundIndex.value,
    node.value,
    viewerOriginal.value,
    showOtherHands.value,
  )
  // 错和不是本局终点：只推进节点，不执行和牌展示，避免牌桌停留在亮牌状态。
  const update = isCuoheTick(tick) ? null : rawUpdate
  const nextPosition = replay.value.build(
    roundIndex.value,
    nextNode,
    viewerOriginal.value,
    showOtherHands.value,
  )
  decorateSnapshotRanks(nextPosition.snapshot)
  decorateEventRanks(update)
  node.value = nextNode
  if (update) {
    const snapshotClaimKinds = new Set(['chow', 'pung', 'melded_kong'])
    if (snapshotClaimKinds.has(String(update.event?.kind || ''))) {
      // A replay already has the authoritative post-claim hand, river and meld
      // in nextPosition. Rebuild those three together so an incremental claim
      // can never leave only the call label without its exposed meld.
      scene.flushFromSnapshot(nextPosition.snapshot)
      scene.applyReplayCue('claim', update.event)
    } else {
      // Even in instant-panel mode, execute the same table-side win event as a
      // normal replay step so the hand reveal and final win audio are preserved.
      scene.handleEvent(update)
    }
    refreshReplayHints(nextPosition.snapshot)
    actionLabel.value = nextPosition.actionLabel
    const seatMap = replay.value.rounds[roundIndex.value].seats || [0, 1, 2, 3]
    currentScores.value = seatMap.map((seat) => nextPosition.snapshot.seats[seat]?.score ?? 0)
    skipNextPositionRender = true
  }
  if (!isCuoheTick(tick) && (action.startsWith('hu_') || action === 'liuju' || action === 'ryuukyoku')) {
    presentTerminalResult(action, Boolean(update))
  }
}

function onBoardStep(delta: number) {
  if (loading.value || errorMessage.value || !sceneReady.value) return
  step(delta)
}

function onBoardWheel(event: WheelEvent) {
  if (loading.value || errorMessage.value || !sceneReady.value || terminalLocked.value || Math.abs(event.deltaY) < 1) return
  stopPlaying()
  resetTerminalPresentation()
  const nodes = currentXunmuNodes.value
  if (event.deltaY > 0) {
    const target = nodes.find((value) => value > node.value)
    if (target != null) {
      node.value = target
    } else if (node.value < maxNode.value) {
      node.value = maxNode.value
    }
  } else {
    const target = [...nodes].reverse().find((value) => value < node.value)
    if (target != null) {
      node.value = target
    } else if (roundIndex.value > 0 && replay.value) {
      roundIndex.value -= 1
      const previousNodes = replay.value.xunmuNodes(roundIndex.value, viewerOriginal.value)
      node.value = previousNodes.at(-1) ?? 0
    }
  }
}

function scoreValuesFromTick(tick: RecordTick): number[] | null {
  const action = String(tick[0] ?? '')
  const value = action === 'ryuukyoku' ? tick[2] : action.startsWith('hu_') ? tick[4] : null
  return Array.isArray(value) && value.length >= 4 ? value.map((item) => Number(item) || 0) : null
}

function terminalTick(round: RecordRound): RecordTick | null {
  return [...(round.action_ticks || [])].reverse().find((tick) => {
    if (isCuoheTick(tick)) return false
    const action = String(tick?.[0] ?? '')
    return action.startsWith('hu_') || action === 'liuju' || action === 'ryuukyoku'
  }) || null
}

function roundOutcomeClass(index: number) {
  const round = replay.value?.rounds[index]
  const terminal = round ? terminalTick(round) : null
  if (!round || !terminal) return ''
  const action = String(terminal[0] ?? '')
  if (action === 'liuju' || action === 'ryuukyoku') return 'is-draw'
  if (!action.startsWith('hu_')) return ''
  const seat = round.seats?.[viewerOriginal.value] ?? viewerOriginal.value
  const winnerSeat = Number(terminal[1])
  if (seat === winnerSeat) return 'is-win'
  const change = scoreValuesFromTick(terminal)?.[seat] ?? 0
  if (change >= 0) return ''
  if (action === 'hu_self') return 'is-tsumo-loss'
  const terminalIndex = (round.action_ticks || []).indexOf(terminal)
  const beforeWin = replay.value?.build(index, Math.max(0, terminalIndex), viewerOriginal.value)
  const discarderSeat = Number(beforeWin?.snapshot.state.last_actor)
  return seat === discarderSeat ? 'is-ron-loss' : ''
}

function roundScoreChangeRows(index: number) {
  if (!replay.value) return []
  const changes = replay.value.roundScoreChangesByOriginal(index)
  return [0, 1, 2, 3].map((original) => {
    const player = detail.value?.players.find((item) => item.original_player_index === original)
      || detail.value?.players[original]
    return {
      original,
      username: player?.username || `玩家 ${original + 1}`,
      change: changes[original] ?? 0,
    }
  })
}

function moveRoundTooltip(index: number, event: MouseEvent) {
  hoveredRoundIndex.value = index
  roundTooltipPosition.value = {
    x: event.clientX - 9,
    y: event.clientY - 9,
  }
}

function showRoundTooltipFromFocus(index: number, event: FocusEvent) {
  hoveredRoundIndex.value = index
  const element = event.currentTarget as HTMLElement | null
  const rect = element?.getBoundingClientRect()
  roundTooltipPosition.value = {
    x: (rect?.left ?? 260) - 9,
    y: (rect?.top ?? 140) - 9,
  }
}

function roundSelectLabel(round: RecordRound, index: number) {
  const number = Number(round.current_round ?? index + 1)
  return tr(roundLabelKey(number, appearance.value.roundLabelFormat, locale.value))
}

function selectRound(index: number) {
  if (terminalLocked.value) return
  stopPlaying()
  resetTerminalPresentation()
  roundIndex.value = index
  node.value = 0
}

function selectXunmu(value: string) {
  if (terminalLocked.value) return
  stopPlaying()
  resetTerminalPresentation()
  if (value === 'end') {
    node.value = maxNode.value
    return
  }
  const index = Math.max(0, Math.min(currentXunmuNodes.value.length - 1, Number(value) || 0))
  node.value = currentXunmuNodes.value[index] ?? 0
}

function jumpToScoreboardRound(index: number) {
  if (!replay.value || index < 0 || index >= replay.value.rounds.length) return
  scoreboardOpen.value = false
  selectRound(index)
}

function changeRound(delta: number) {
  if (!replay.value) return
  selectRound(Math.max(0, Math.min(replay.value.rounds.length - 1, roundIndex.value + delta)))
}

function renderPosition() {
  if (!scene || !replay.value) return
  const position = replay.value.build(
    roundIndex.value,
    node.value,
    viewerOriginal.value,
    showOtherHands.value,
  )
  decorateSnapshotRanks(position.snapshot)
  actionLabel.value = position.actionLabel
  const seatMap = replay.value.rounds[roundIndex.value].seats || [0, 1, 2, 3]
  currentScores.value = seatMap.map((seat) => position.snapshot.seats[seat]?.score ?? 0)
  scene.flushFromSnapshot(position.snapshot)
  refreshReplayHints(position.snapshot)
  if (roundResult.value) {
    const action = roundResult.value.action
    presentTerminalResult(action)
  } else if (resultPanelVisible.value || resultTimers.length) {
    resetTerminalPresentation()
  }
}

function meldKey(meld: MeldSnapshot): string {
  const tile = mmcrTileToSalasasa(meld.tile)
  if (meld.type === 'sequence') return `s${tile}`
  if (meld.type === 'triplet') return `k${tile}`
  return `${meld.concealed ? 'G' : 'g'}${tile}`
}

function waitDataForSnapshot(snapshot: ActiveSessionSnapshot) {
  const viewer = snapshot.seats.find((seat) => seat.seat_index === snapshot.viewer.seat_index)
  if (!viewer?.hand_tiles) return null
  const hand = viewer.hand_tiles.map(mmcrTileToSalasasa)
  if (viewer.drawn_tile != null) hand.push(mmcrTileToSalasasa(viewer.drawn_tile))
  const title = detail.value?.record.game_title ?? {}
  return buildLocalWaitData({
    tips: true,
    hand,
    combinations: viewer.melds.map(meldKey),
    flowerCount: viewer.flower_tiles?.length ?? 0,
    playerIndex: viewer.seat_index,
    currentRound: Number(currentRound.value?.current_round ?? roundIndex.value + 1),
    hepaiLimit: Number(title.hepai_limit ?? 8),
    subRule: String(detail.value?.sub_rule ?? 'guobiao'),
    seatDiscards: snapshot.seats.map((seat) => seat.discard_pile.map(mmcrTileToSalasasa)),
    seatCombinations: snapshot.seats.map((seat) => seat.melds.map(meldKey)),
  }, { includeDiscards: viewer.drawn_tile != null })
}

function waitingTilesForSnapshotSeat(seat: ActiveSessionSnapshot['seats'][number]): Set<number> {
  const hand = (seat.hand_tiles ?? []).map(mmcrTileToSalasasa)
  if (hand.length === 0) return new Set<number>()
  try {
    const waits = tingpaiCheck(hand, seat.melds.map(meldKey), false)
    return new Set(waits.map(salasasaTileToMmcr))
  } catch {
    return new Set<number>()
  }
}

function waitingForDrawAfterCut(snapshot: ActiveSessionSnapshot): boolean {
  const ticks = currentRound.value?.action_ticks ?? []
  for (let index = Math.min(node.value, ticks.length) - 1; index >= 0; index -= 1) {
    const action = String(ticks[index]?.[0] ?? '')
    if (!action || ['ask_hand', 'ask_other', 'ca'].includes(action)) continue
    return action === 'c'
  }
  return snapshot.state.last_event_kind === 'discard_tile'
}

function refreshReplayHints(snapshot: ActiveSessionSnapshot) {
  const waitData = waitDataForSnapshot(snapshot)
  if (waitData?.type === 'waits') {
    scene?.setReplayWaitTips({
      type: 'waits',
      details: waitData.details.map((item) => ({ ...item, tile: salasasaTileToMmcr(item.tile) })),
    })
  } else if (waitData?.type === 'waits_all') {
    scene?.setReplayWaitTips({
      type: 'waits_all',
      details: waitData.details.map((item) => ({
        discard_tile: salasasaTileToMmcr(item.discard_tile),
        adds: item.adds.map((add) => ({ ...add, tile: salasasaTileToMmcr(add.tile) })),
      })),
    })
  } else {
    scene?.setReplayWaitTips(null)
  }
  scene?.setReplayDangerTiles(replayDangerBySeat.value)
}

function decorateSnapshotRanks(snapshot: ActiveSessionSnapshot) {
  for (const seat of snapshot.seats) {
    seat.rank = seat.player_id == null ? '—' : currentRanks.value[String(seat.player_id)] || '—'
  }
}

function decorateEventRanks(update: Record<string, any> | null) {
  if (!update || !Array.isArray(update.seat_status)) return
  for (const seat of update.seat_status) {
    seat.rank = seat.user_id == null ? '—' : currentRanks.value[String(seat.user_id)] || '—'
  }
}

async function loadCurrentRanks(record: PublicGameRecord) {
  const entries = await Promise.all(record.players.map(async (player) => {
    try {
      const profile = await publicApiGet<{ rank?: { guobiao_rank?: string | null } }>(
        playerProfileUrl(player.user_id),
      )
      return [String(player.user_id), profile.rank?.guobiao_rank || '—'] as const
    } catch {
      return [String(player.user_id), '—'] as const
    }
  }))
  currentRanks.value = Object.fromEntries(entries)
}

function toggleOtherHands() {
  showOtherHands.value = !showOtherHands.value
  renderPosition()
}

function toggleChongHint() {
  chongHintEnabled.value = !chongHintEnabled.value
  if (resultPosition.value?.snapshot) {
    scene?.setReplayDangerTiles(replayDangerBySeat.value)
  }
}

function toggleMoqieHint() {
  showMoqieMode.value = !showMoqieMode.value
  scene?.setReplayMoqieHintEnabled(showMoqieMode.value)
  renderPosition()
}

function onGameInfoWheel(event: WheelEvent) {
  const element = gameInfoScrollElement.value
  if (!element) return
  const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
    ? 16
    : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
      ? element.clientHeight
      : 1
  element.scrollTop += event.deltaY * unit * 0.5
}

function mmcrTileAsset(tid: number) {
  const suit = Number(tid) & 0xe0
  const rank = Number(tid) & 0x0f
  let prefix = 'z'
  if (suit === 0x40) prefix = 'Man'
  else if (suit === 0x60) prefix = 'Pin'
  else if (suit === 0xc0) prefix = 'Sou'
  else if (suit === 0xe0) prefix = 'Flower'
  const folder = appearance.value.tileFaceTheme === 'black' && prefix !== 'Flower' ? 'Black' : 'Regular'
  if (prefix === 'Flower' && appearance.value.flowerFaceTheme === 'unity') {
    return `${import.meta.env.BASE_URL}game2d-assets/textures/riichi-mahjong-tiles/Unity/${prefix}${rank}.png`
  }
  return `${import.meta.env.BASE_URL}game2d-assets/textures/riichi-mahjong-tiles/${folder}/${prefix}${rank}.svg`
}

function persistAppearance(next: typeof appearance.value) {
  appearance.value = normalizeSceneAppearanceSettings(next)
  saveStoredSceneAppearance(appearance.value)
  scene?.setAppearance(appearance.value)
}

function setAppearanceField(field: keyof typeof appearance.value, value: unknown) {
  persistAppearance({ ...appearance.value, [field]: value })
}

function setTileCoverColor(index: number, color: string) {
  const colors = [...appearance.value.tileCoverColors]
  colors[index] = color
  persistAppearance({ ...appearance.value, tileCoverColors: colors })
}

function addTileCoverColor() {
  const colors = appearance.value.tileCoverColors
  if (colors.length >= MAX_TILE_COVER_COLORS) return
  persistAppearance({
    ...appearance.value,
    tileCoverColors: [...colors, colors.at(-1) ?? '#f6bc1e'],
  })
}

function removeTileCoverColor(index: number) {
  if (appearance.value.tileCoverColors.length <= 1) return
  const currentIndex = appearance.value.lastTileCoverIndex
  const colors = appearance.value.tileCoverColors.filter((_, colorIndex) => colorIndex !== index)
  const nextIndex = index < currentIndex
    ? currentIndex - 1
    : index === currentIndex ? Math.min(index, colors.length - 1) : currentIndex
  persistAppearance({ ...appearance.value, tileCoverColors: colors, lastTileCoverIndex: nextIndex })
}

function reorderTileCoverColors(colors: string[], activeIndex: number) {
  persistAppearance({ ...appearance.value, tileCoverColors: colors, lastTileCoverIndex: activeIndex })
}

function selectTileCoverIndex(index: number) {
  persistAppearance({ ...appearance.value, lastTileCoverIndex: index })
  scene?.setActiveTileCoverIndex(index)
}

async function uploadBackgroundImage(file: File) {
  try {
    backgroundImage.value = await saveStoredSceneBackgroundImage(file)
    persistAppearance({ ...appearance.value, backgroundImageEnabled: true })
    scene?.setBackgroundImage(backgroundImage.value.dataUrl)
  } catch {
    ElMessage.error('背景图片保存失败')
  }
}

async function clearBackgroundImage() {
  try {
    await clearStoredSceneBackgroundImage()
    backgroundImage.value = null
    persistAppearance({ ...appearance.value, backgroundImageEnabled: false })
    scene?.setBackgroundImage(null)
  } catch {
    ElMessage.error('背景图片移除失败')
  }
}

async function resetAppearance() {
  resetStoredSceneAppearance()
  try { await clearStoredSceneBackgroundImage() } catch { /* IndexedDB 不可用时仍可重置 */ }
  appearance.value = {
    ...DEFAULT_SCENE_APPEARANCE,
    tileCoverColors: [...DEFAULT_SCENE_APPEARANCE.tileCoverColors],
  }
  backgroundImage.value = null
  scene?.setAppearance(appearance.value)
  scene?.setBackgroundImage(null)
}

function changeVolume(next: number) {
  volume.value = Number(next)
  saveStoredVolume(volume.value)
  scene?.setVolume(volume.value)
}

async function copyShareLink(kind: '2d' | '3d' | 'node') {
  const gameId = String(detail.value?.game_id || route.params.gameId)
  const path = kind === '3d'
    ? `/game-unity?recordId=${encodeURIComponent(gameId)}`
    : kind === 'node'
      ? `/2d/record/${encodeURIComponent(gameId)}?round=${roundIndex.value + 1}&node=${node.value}`
      : `/2d/record/${encodeURIComponent(gameId)}`
  const url = new URL(path, window.location.origin).toString()
  try {
    await navigator.clipboard.writeText(url)
    copiedKind.value = kind
    if (kind === 'node') {
      ElMessage.success(`已复制当前位置链接（第${roundIndex.value + 1}局 node ${node.value}）`)
    }
    window.setTimeout(() => {
      if (copiedKind.value === kind) copiedKind.value = null
    }, 1800)
  } catch {
    ElMessage.error(`复制失败，请手动复制：${url}`)
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.target instanceof HTMLInputElement) return
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    event.shiftKey ? changeRound(-1) : step(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    event.shiftKey ? changeRound(1) : step(1)
  } else if (event.code === 'Space') {
    event.preventDefault()
    togglePlaying()
  }
}

async function mountScene() {
  if (!stageElement.value || scene) return
  const currentScene = new MahjongScene(() => {})
  currentScene.setPresentationMode('replay')
  currentScene.setReplayRecordVersion(6)
  currentScene.setReplayMoqieHintEnabled(showMoqieMode.value)
  currentScene.setReplayWaitTips(null)
  currentScene.setVolume(volume.value)
  currentScene.setAppearance(appearance.value)
  for (const sound of GAME_SOUND_ASSETS) {
    const audio = new Audio(getPreloadedSoundUrl(sound.file))
    audio.preload = 'auto'
    audio.load()
    currentScene.loadSound(sound.alias, audio)
  }
  scene = currentScene
  const mounted = await currentScene.mount(stageElement.value)
  if (!mounted || scene !== currentScene) return
  try {
    backgroundImage.value = await loadStoredSceneBackgroundImage()
    currentScene.setBackgroundImage(backgroundImage.value?.dataUrl ?? null)
  } catch {
    backgroundImage.value = null
    currentScene.setBackgroundImage(null)
  } finally {
    backgroundImageLoading.value = false
  }
  sceneReady.value = true
  await nextTick()
  currentScene.forceResize()
  renderPosition()
}

/**
 * 本地静态 JSON（public/records/{gameId}.json）优先；其次浏览器暂存的本地牌谱；
 * 最后兜底远程平台 API（publicRecordUrl）。
 */
async function fetchRecord(gameId: string): Promise<{ value: PublicGameRecord; local: boolean }> {
  const stored = loadLocalReplayRecord(gameId)
  if (stored) return { value: stored, local: true }
  const response = await fetch(
    `${import.meta.env.BASE_URL}records/${encodeURIComponent(gameId)}.json`,
    { headers: { Accept: 'application/json' } },
  )
  if (response.ok) return { value: await response.json() as PublicGameRecord, local: true }
  return { value: await publicApiGet<PublicGameRecord>(publicRecordUrl(gameId)), local: false }
}

/**
 * 后端返回的 record 可能是 {game_round} 内层、平台原格式或完整 PublicGameRecord，
 * 统一规整为前端 RecordReplay 需要的 PublicGameRecord。
 */
function toPublicGameRecord(
  source: Record<string, unknown>,
  fallbackGameId: string,
  metaPlayers?: PrepareResult['meta']['players'],
): PublicGameRecord {
  const sourceRecord = source.record
  const gameRound = (sourceRecord != null && typeof sourceRecord === 'object' && (sourceRecord as Record<string, unknown>).game_round != null
    ? sourceRecord
    : source.game_round != null ? source : {}) as Record<string, unknown>
  const rawPlayers = Array.isArray(source.players) ? source.players as Record<string, unknown>[] : metaPlayers ?? []
  return {
    game_id: String(source.game_id ?? fallbackGameId),
    created_at: String(source.created_at ?? ''),
    rule: String(source.rule ?? 'guobiao'),
    sub_rule: source.sub_rule != null ? String(source.sub_rule) : null,
    room_type: source.room_type != null ? String(source.room_type) : null,
    match_type: source.match_type != null ? String(source.match_type) : null,
    players: rawPlayers.map((player, index) => ({
      user_id: Number(player.user_id ?? 0),
      username: String(player.username ?? `玩家 ${index + 1}`),
      score: Number(player.score ?? 0),
      rank: Number(player.rank ?? 0),
      original_player_index: Number(player.original_player_index ?? player.original ?? index),
    })),
    record: { game_round: gameRound.game_round as Record<string, RecordRound> },
  }
}

function buildAiNodeMaps(prepMeta: PrepareResult['meta'] | null) {
  aiNodeMaps = null
  if (!prepMeta || !replay.value) return
  const indexByRoundNumber = new Map<number, number>()
  replay.value.rounds.forEach((round, index) => {
    indexByRoundNumber.set(Number(round.round_index ?? index + 1), index)
  })
  const maps = new Map<number, Map<number, Map<number, number>>>()
  for (const metaRound of prepMeta.rounds) {
    const frontIndex = indexByRoundNumber.get(Number(metaRound.round_index))
    if (frontIndex == null) continue
    const ticks = replay.value.rounds[frontIndex].action_ticks || []
    const perViewer = new Map<number, Map<number, number>>()
    for (let viewer = 0; viewer < 4; viewer += 1) {
      const discardToStep = new Map<number, number>()
      const viewerMeta = metaRound.viewers[String(viewer)]
      if (viewerMeta && !viewerMeta.error) {
        for (const node of viewerMeta.nodes) {
          for (let tick = node.step + 1; tick < ticks.length; tick += 1) {
            if (String(ticks[tick]?.[0] ?? '') === 'c') {
              discardToStep.set(tick, node.step)
              break
            }
          }
        }
      }
      perViewer.set(viewer, discardToStep)
    }
    maps.set(frontIndex, perViewer)
  }
  aiNodeMaps = maps
}

async function requestAi() {
  const step = aiStepForCurrentTick.value
  if (!analysisId.value || step == null || !currentRound.value) {
    aiData.value = null
    aiError.value = ''
    aiLoading.value = false
    return
  }
  const requestId = ++aiRequestId
  aiLoading.value = true
  try {
    const backendRound = Number(currentRound.value.round_index ?? roundIndex.value + 1)
    const result = await fetchStep(analysisId.value, backendRound, step, viewerOriginal.value)
    if (requestId !== aiRequestId) return
    aiData.value = result
    aiError.value = ''
  } catch (error) {
    if (requestId !== aiRequestId) return
    aiData.value = null
    aiError.value = error instanceof AiApiError && error.status === 503
      ? 'AI 模型未加载，回放不受影响'
      : `AI 请求失败（${error instanceof Error ? error.message : String(error)}）`
  } finally {
    if (requestId === aiRequestId) aiLoading.value = false
  }
}

async function startReplay(record: PublicGameRecord, prepMeta: PrepareResult['meta'] | null) {
  replay.value = new RecordReplay(record)
  detail.value = record
  roundIndex.value = 0
  node.value = 0
  viewerOriginal.value = 0
  showOtherHands.value = true
  playWinAnimation.value = false
  chongHintEnabled.value = true
  showMoqieMode.value = true
  wallVisible.value = false
  scoreboardOpen.value = false
  settingsOpen.value = false
  aiData.value = null
  aiError.value = ''
  buildAiNodeMaps(prepMeta)
  applyDeepLinkPosition()
  await nextTick()
  await mountScene()
  renderPosition()
}

function showInputPage() {
  stopPlaying()
  resetTerminalPresentation()
  analysisId.value = null
  aiData.value = null
  aiError.value = ''
  aiNodeMaps = null
  replay.value = null
  detail.value = null
  sceneReady.value = false
  scene?.destroy()
  scene = null
  errorMessage.value = ''
  inputPage.value = true
  loading.value = false
}

/** 输入解析：支持纯 game_id、2D 回放链接（/2d/record/{id}）、Unity 回放链接（?recordId={id}）。 */
function parseGameIdOrUrl(raw: string): string | null {
  const s = raw.trim()
  const m2d = s.match(/\/2d\/record\/([A-Za-z0-9_-]+)/)
  if (m2d) return m2d[1]
  const mq = s.match(/[?&]recordId=([A-Za-z0-9_-]+)/)
  if (mq) return mq[1]
  if (/^[A-Za-z0-9]+$/.test(s)) return s
  return null
}

async function submitInput() {
  const trimmed = recordJsonInput.value.trim()
  let payload: { game_id?: string; platform?: string; record?: unknown }
  let gid = ''
  if (trimmed) {
    let parsed: unknown
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      inputError.value = '牌谱 JSON 解析失败'
      return
    }
    payload = { record: parsed }
  } else if (gameIdInput.value.trim()) {
    gid = parseGameIdOrUrl(gameIdInput.value) ?? ''
    if (!gid) {
      inputError.value = '无法识别的对局 ID/链接（支持纯 ID、2D 回放链接、Unity 回放链接）'
      return
    }
    payload = {
      game_id: gid,
      platform: platformInput.value.trim() || undefined,
    }
  } else {
    inputError.value = '请输入对局 ID 或粘贴牌谱 JSON'
    return
  }
  preparing.value = true
  inputError.value = ''
  try {
    const prepared = await prepareAnalysis(payload)
    analysisId.value = prepared.analysis_id
    const publicRecord = toPublicGameRecord(
      prepared.record,
      gid || gameIdInput.value.trim() || String(prepared.meta.game_id || 'upload'),
      prepared.meta.players,
    )
    inputPage.value = false
    await startReplay(publicRecord, prepared.meta)
  } catch (error) {
    inputError.value = error instanceof Error ? error.message : '准备牌谱失败'
  } finally {
    preparing.value = false
  }
}

const AI_SUIT_PREFIX: Record<string, number> = { W: 1, T: 2, B: 3, F: 4 }
/** IJCAI 字牌 J1=中 J2=发 J3=白 → salasasa 字牌 rank z5/z6/z7（45中 46白 47发）。 */
const AI_HONOR_RANK: Record<string, number> = { J1: 5, J2: 7, J3: 6 }

function aiTileToMmcr(tile: string): number {
  const honor = AI_HONOR_RANK[String(tile ?? '')]
  if (honor) return salasasaTileToMmcr(40 + honor)
  const prefix = String(tile?.[0] ?? '')
  const rank = Number(String(tile ?? '').slice(1))
  const suit = AI_SUIT_PREFIX[prefix]
  if (!suit || !Number.isFinite(rank)) return 0
  const maxRank = prefix === 'F' ? 4 : 9
  if (rank < 1 || rank > maxRank) return 0
  return salasasaTileToMmcr(suit * 10 + rank)
}

function aiTileLabel(tile: string): string {
  const prefix = String(tile?.[0] ?? '')
  const rank = Number(String(tile ?? '').slice(1))
  const winds = ['东', '南', '西', '北']
  const honors = ['中', '发', '白']
  if (prefix === 'F' && rank >= 1 && rank <= 4) return winds[rank - 1]
  if (prefix === 'J' && rank >= 1 && rank <= 3) return honors[rank - 1]
  const names: Record<string, string> = { W: '万', T: '筒', B: '条' }
  return names[prefix] ? `${rank}${names[prefix]}` : String(tile ?? '—')
}

async function loadRecord() {
  const gameId = String(route.params.gameId || '')
  if (!gameId) {
    loading.value = false
    showInputPage()
    return
  }
  loading.value = true
  errorMessage.value = ''
  stopPlaying()
  resetTerminalPresentation()
  try {
    try {
      const prepared = await prepareAnalysis({ game_id: gameId })
      analysisId.value = prepared.analysis_id
      const publicRecord = toPublicGameRecord(prepared.record, gameId, prepared.meta.players)
      await startReplay(publicRecord, prepared.meta)
      return
    } catch {
      // 后端不可用/平台拉取失败时走本地兜底（无 AI 分析）
      const { value, local } = await fetchRecord(gameId)
      analysisId.value = null
      if (local) currentRanks.value = {}
      else await loadCurrentRanks(value)
      await startReplay(value, null)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '牌谱读取失败'
  } finally {
    loading.value = false
  }
}

/**
 * 分享链接形如 /2d/record/{gameId}?round={第几局，从 1 开始}&node={节点下标，从 0 开始}。
 * 打开链接时直接跳转到对应局数与节点；参数缺失或越界时回退到开头。
 */
function applyDeepLinkPosition() {
  if (!replay.value) return
  const rawRound = Number(route.query.round)
  if (Number.isFinite(rawRound) && rawRound >= 1) {
    const targetRound = Math.min(replay.value.rounds.length - 1, Math.floor(rawRound) - 1)
    roundIndex.value = Math.max(0, targetRound)
  }
  const rawNode = Number(route.query.node)
  if (Number.isFinite(rawNode) && rawNode >= 0) {
    const ticks = replay.value.rounds[roundIndex.value]?.action_ticks ?? []
    node.value = Math.max(0, Math.min(ticks.length, Math.floor(rawNode)))
  }
}

watch([roundIndex, node, viewerOriginal], () => {
  if (node.value > maxNode.value) node.value = maxNode.value
  if (skipNextPositionRender) {
    skipNextPositionRender = false
    return
  }
  renderPosition()
})
watch([roundIndex, node, viewerOriginal], requestAi)
watch(locale, () => {
  scene?.refreshRoundLabel()
})
watch(() => route.params.gameId, loadRecord)

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  void loadRecord()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  stopPlaying()
  clearResultTimers()
  scene?.destroy()
  scene = null
})
</script>

<style src="./Game.css"></style>
<style src="./Replay.css"></style>
