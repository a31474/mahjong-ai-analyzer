export interface AiTopEntry {
  tile: string
  prob: number
}

/** claim 决策点的一个候选动作：pass/hu/chi/peng/gang；chi 的 tile 是顺子中间张。 */
export interface AiClaimAction {
  action: 'pass' | 'hu' | 'chi' | 'peng' | 'gang'
  tile: string | null
  index: number
  prob: number
}

export interface AiStepResult {
  kind?: 'discard' | 'claim'
  step: number
  player: number
  seat: number
  agree: boolean
  error?: string
  // kind='discard'（自己摸/鸣牌后待打牌）
  actual_tile?: string
  ai_top?: AiTopEntry[]
  // kind='claim'（别人打牌后本家可吃/碰/杠/和/过）
  claim_tile?: string
  actual_action?: 'pass' | 'hu' | 'chi' | 'peng' | 'gang'
  cuohe?: boolean
  ai_actions?: AiClaimAction[]
}

export interface PrepareResult {
  analysis_id: string
  meta: {
    game_id: string
    players: Array<{ original?: number; user_id?: number; username?: string }>
    rounds: Array<{
      round_index: number
      viewers: Record<string, {
        error?: string | null
        nodes: Array<{ step: number; kind?: 'discard' | 'claim'; actual_action?: string }>
      }>
    }>
  }
  record: Record<string, unknown>
}

export class AiApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function fetchWithTimeout(url: string, init: RequestInit, timeoutMs = 15000): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  return fetch(url, { ...init, signal: controller.signal }).catch((error: unknown) => {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new AiApiError(0, '请求超时')
    }
    throw error
  }).finally(() => {
    window.clearTimeout(timer)
  })
}

export async function prepareAnalysis(
  payload: { game_id?: string; platform?: string; record?: unknown },
): Promise<PrepareResult> {
  const response = await fetchWithTimeout('/api/analyze/prepare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null
    throw new AiApiError(response.status, detail?.detail || `prepare failed: ${response.status}`)
  }
  return response.json()
}

export async function fetchStep(
  analysisId: string,
  round: number,
  step: number,
  viewer: number,
): Promise<AiStepResult> {
  const query = new URLSearchParams({
    round: String(round),
    step: String(step),
    viewer: String(viewer),
  })
  const response = await fetchWithTimeout(`/api/analysis/${encodeURIComponent(analysisId)}/step?${query}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null) as { detail?: string } | null
    throw new AiApiError(response.status, detail?.detail || `step failed: ${response.status}`)
  }
  return response.json()
}
