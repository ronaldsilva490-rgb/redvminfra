// ══════════════════════════════════════════════════
// PROXY — Conexão WebSocket com RED Claude
// ══════════════════════════════════════════════════
const WebSocket = require('ws')
const {
    eventEmitter, activeRedRequests, jidProcessingState,
    waSessionDispatchState, realtimeStreamState, activeStatusMessages,
    sessionContextSent
} = require('./state')

let proxySocket = null
const proxyUrl = process.env.RED_PROXY_URL || 'ws://redsystems.ddns.net:11434'

// Forward declarations — set by messageHandler after load
let _handleStatusUpdate = null
let _startRealtimeComposing = null
let _clearJidTimeouts = null

function setProxyHandlers({ handleStatusUpdate, startRealtimeComposing, clearJidTimeouts }) {
    _handleStatusUpdate = handleStatusUpdate
    _startRealtimeComposing = startRealtimeComposing
    _clearJidTimeouts = clearJidTimeouts
}

function getProxySocket() { return proxySocket }

function initProxyConnection() {
    if (proxySocket && (proxySocket.readyState === WebSocket.OPEN || proxySocket.readyState === WebSocket.CONNECTING)) return

    console.log(`[PROXY] Conectando ao RED Proxy: ${proxyUrl}`)
    proxySocket = new WebSocket(proxyUrl)

    proxySocket.onopen = () => {
        console.log(`[PROXY] Conectado ao RED Proxy com sucesso.`)

        if (activeRedRequests.size > 0) {
            console.warn(`[PROXY] 🔓 Limpando ${activeRedRequests.size} sessão(ões) travada(s) no activeRedRequests`)
            activeRedRequests.clear()
        }
        for (const [key, st] of jidProcessingState) {
            if (st.processing) {
                console.warn(`[PROXY] 🔓 Liberando fila travada após reconexão: ${key}`)
                if (_clearJidTimeouts) _clearJidTimeouts(st)
                st.processing = false
                st.awaitingUserConfirm = false
                st.queue = []
            }
        }

        proxySocket.send(JSON.stringify({
            action: 'STATUS',
            agent: 'LOCAL_FRONTEND',
            sessionId: 'WHATSAPP_SERVICE'
        }))
    }

    proxySocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data)

            if (data.action === 'NEURAL_STATUS' && typeof data.sessionId === 'string' && data.sessionId.startsWith('WA_')) {
                try {
                    const state = waSessionDispatchState.get(data.sessionId)
                    if (state?.sock && state?.remoteJid) {
                        const tenantId = String(data.sessionId).replace(/^WA_/, '').split('_')[0] || 'default'
                        const statusText = typeof data.status === 'string' && data.status.trim()
                            ? data.status
                            : (typeof data.rawStatus === 'string' ? data.rawStatus : '')
                        if (statusText && !activeRedRequests.has(data.sessionId) && _handleStatusUpdate) {
                            _handleStatusUpdate(tenantId, state.remoteJid, statusText).catch(() => {})
                        }
                        const streamKey = `${tenantId}::${state.remoteJid}`
                        const streamState = realtimeStreamState.get(streamKey)
                        const sessionStillActive = activeRedRequests.has(data.sessionId)
                        if (sessionStillActive && _startRealtimeComposing) {
                            if (streamState) streamState.stopped = false
                            _startRealtimeComposing(state.sock, state.remoteJid, streamKey)
                        }
                    }
                } catch (_) {}
            }

            if (data.action === 'NEURAL_COMPLETE') {
                console.log(`[PROXY] Recebido: ${data.action} | sessionId: ${data.sessionId} | text length: ${(data.text||'').length}`)
            }
            if (data.action === 'STATUS' && data.agent === 'RED_CLAUDE_EXTENSION' && data.status === 'READY') {
                console.log(`[PROXY] Extensão reconectada (${data.instanceId}). Resetando contexto de sessões...`)
                sessionContextSent.clear()
            }
            if (data.action === 'STREAM_STATUS' && data.status) {
                data.action = 'NEURAL_STATUS'
                data.rawStatus = data.status
            }

            eventEmitter.emit('proxy_message', data)
        } catch (e) {
            console.error(`[PROXY] ❌ Falha ao processar mensagem JSON:`, e.message)
        }
    }

    proxySocket.onclose = () => {
        console.log(`[PROXY] Conexão fechada. Tentando reconectar em 5s...`)
        setTimeout(initProxyConnection, 5000)
    }

    proxySocket.onerror = (err) => {
        console.error(`[PROXY] Erro na conexão:`, err.message)
    }
}

module.exports = {
    initProxyConnection, getProxySocket, setProxyHandlers, WebSocket
}
