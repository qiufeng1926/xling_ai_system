export interface RecordingPipState {
  title: string
  meetingName: string
  elapsedLabel: string
  disconnected: boolean
}

let pipWindow: Window | null = null
let popupWindow: Window | null = null

const PIP_STYLE = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    background: linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%);
    color: #fff;
    padding: 14px 16px;
    min-height: 100vh;
  }
  .dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: #f56c6c; display: inline-block; margin-right: 8px;
    animation: pulse 1.2s ease-in-out infinite;
  }
  .dot.warn { background: #e6a23c; animation: none; }
  .title { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
  .name { font-size: 12px; opacity: 0.9; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .time { font-size: 13px; font-variant-numeric: tabular-nums; opacity: 0.92; margin-bottom: 10px; }
  button {
    width: 100%; padding: 8px 12px; border: none; border-radius: 6px;
    background: rgba(255,255,255,0.15); color: #fff; font-size: 13px; cursor: pointer;
  }
  button:hover { background: rgba(255,255,255,0.25); }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
  }
`

export function isDocumentPipSupported(): boolean {
  return typeof window !== 'undefined' && 'documentPictureInPicture' in window
}

export function isRecordingPipOpen(): boolean {
  if (pipWindow && !pipWindow.closed) return true
  if (popupWindow && !popupWindow.closed) return true
  return false
}

function renderPipDocument(doc: Document, state: RecordingPipState) {
  const dotClass = state.disconnected ? 'dot warn' : 'dot'
  const nameHtml = state.meetingName
    ? `<div class="name">${escapeHtml(state.meetingName)}</div>`
    : ''
  const timeHtml = state.elapsedLabel
    ? `<div class="time">${escapeHtml(state.elapsedLabel)}</div>`
    : ''
  doc.body.innerHTML = `
    <style>${PIP_STYLE}</style>
    <div class="title"><span class="${dotClass}"></span>${escapeHtml(state.title)}</div>
    ${nameHtml}
    ${timeHtml}
    <button type="button" id="xlink-pip-focus">返回 xlink</button>
  `
  doc.getElementById('xlink-pip-focus')?.addEventListener('click', () => {
    window.focus()
  })
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function openPopupFallback(state: RecordingPipState): boolean {
  const features = 'width=300,height=150,menubar=no,toolbar=no,location=no,status=no,resizable=yes'
  const popup = window.open('/recording-pip.html', 'xlink-recording-pip', features)
  if (!popup) return false
  popupWindow = popup
  const postUpdate = () => {
    if (popup.closed) {
      popupWindow = null
      return
    }
    popup.postMessage({ type: 'xlink:pip-update', ...state }, window.location.origin)
  }
  popup.addEventListener('load', postUpdate)
  setTimeout(postUpdate, 300)
  return true
}

export async function openRecordingPip(state: RecordingPipState): Promise<boolean> {
  if (isRecordingPipOpen()) {
    updateRecordingPip(state)
    return true
  }

  if (isDocumentPipSupported()) {
    try {
      const pipApi = (window as Window & {
        documentPictureInPicture: {
          requestWindow: (opts: { width: number; height: number }) => Promise<Window>
        }
      }).documentPictureInPicture
      const height = state.meetingName ? 150 : 130
      pipWindow = await pipApi.requestWindow({ width: 300, height })
      renderPipDocument(pipWindow.document, state)
      pipWindow.addEventListener('pagehide', () => {
        pipWindow = null
      })
      return true
    } catch {
      pipWindow = null
    }
  }

  return openPopupFallback(state)
}

export function updateRecordingPip(state: RecordingPipState) {
  if (pipWindow && !pipWindow.closed) {
    renderPipDocument(pipWindow.document, state)
  }
  if (popupWindow && !popupWindow.closed) {
    popupWindow.postMessage({ type: 'xlink:pip-update', ...state }, window.location.origin)
  }
}

export function closeRecordingPip() {
  try {
    pipWindow?.close()
  } catch {
    /* ignore */
  }
  try {
    popupWindow?.close()
  } catch {
    /* ignore */
  }
  pipWindow = null
  popupWindow = null
}

let notificationShownForSession = false

export async function notifyBackgroundRecording(title: string) {
  if (notificationShownForSession) return
  if (!('Notification' in window)) return
  let permission = Notification.permission
  if (permission === 'default') {
    permission = await Notification.requestPermission()
  }
  if (permission !== 'granted') return
  notificationShownForSession = true
  const n = new Notification('xlink 正在后台录音', {
    body: `${title}。可点击「屏幕置顶」在其他网页时查看状态。`,
    tag: 'xlink-recording',
    requireInteraction: false,
  })
  n.onclick = () => {
    window.focus()
    n.close()
  }
}

export function resetRecordingPipSession() {
  notificationShownForSession = false
  closeRecordingPip()
}
