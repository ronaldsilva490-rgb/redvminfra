// ══════════════════════════════════════════════════
// QUEUE — Fila de processamento por JID
// ══════════════════════════════════════════════════
const { jidProcessingState } = require('./state')

function getJidState(tenantId, remoteJid) {
    const key = `${tenantId}_${remoteJid}`
    if (!jidProcessingState.has(key)) {
        jidProcessingState.set(key, {
            processing: false,
            queue: [],
            timeoutWarning: null,
            timeoutAsk: null,
            awaitingUserConfirm: false,
            lastStreamEventAt: 0
        })
    }
    return jidProcessingState.get(key)
}

function clearJidTimeouts(state) {
    if (state.timeoutWarning) { clearTimeout(state.timeoutWarning); state.timeoutWarning = null }
    if (state.timeoutAsk)     { clearTimeout(state.timeoutAsk);     state.timeoutAsk     = null }
}

module.exports = { getJidState, clearJidTimeouts }
