// ╔══════════════════════════════════════════════════════════════════════╗
// ║         RED SYSTEM'S WHATSAPP INTEGRATION MODULE                    ║
// ║         v5.0 — Modularizado                                         ║
// ╠══════════════════════════════════════════════════════════════════════╣
// ║ Estrutura:                                                          ║
// ║   src/state.js          — Singletons globais (Maps, Sets, consts)   ║
// ║   src/config.js         — Loader de ai_config.json                  ║
// ║   src/proxy.js          — WebSocket RED Claude                      ║
// ║   src/tts.js            — Text-to-Speech (Edge + eSpeak)            ║
// ║   src/stickers.js       — Reações e stickers                        ║
// ║   src/memory.js         — Memória de longo prazo (Supabase)         ║
// ║   src/media.js          — STT / Vision / File processing            ║
// ║   src/context.js        — Contexto de conversa + empresa            ║
// ║   src/aiProvider.js     — Multi-provider IA                         ║
// ║   src/sender.js         — Envio inteligente + presence              ║
// ║   src/queue.js          — Fila de processamento por JID             ║
// ║   src/proactive.js      — LEARN + Realtime proativo                 ║
// ║   src/messageHandler.js — Listener principal de mensagens           ║
// ║   src/connection.js     — Baileys setup + QR + reconexão            ║
// ║   src/routes.js         — API Express                               ║
// ╚══════════════════════════════════════════════════════════════════════╝

const express = require('express')
const cors = require('cors')

// ── Importa módulos ──
const { VERSION, CHANGELOG, supabase, sessions } = require('./src/state')
const { initProxyConnection, setProxyHandlers } = require('./src/proxy')
const { startRealtimeComposing, handleStatusUpdate } = require('./src/sender')
const { clearJidTimeouts } = require('./src/queue')
const { autoStartSavedSessions } = require('./src/connection')
const { setupRoutes } = require('./src/routes')
const { getAIResponse } = require('./src/aiProvider')
const { sendSmartResponse } = require('./src/sender')

// ── Wiring: resolve dependências circulares ──
setProxyHandlers({ handleStatusUpdate, startRealtimeComposing, clearJidTimeouts })

// ── Express setup ──
const app = express()
app.use(cors())
app.use(express.json({ limit: '50mb' }))

// ── Monta rotas ──
setupRoutes(app)

// ── Inicia proxy RED Claude ──
initProxyConnection()

// ── Mensagens agendadas ──
async function runScheduledMessages() {
    try {
        const now = new Date()
        const currentTime = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
        const currentDay = ['dom','seg','ter','qua','qui','sex','sab'][now.getDay()]

        const { data: schedules } = await supabase
            .from('whatsapp_schedules').select('*').eq('enabled', true).eq('send_time', currentTime)

        if (!schedules?.length) return

        const { lastProactiveTime } = require('./src/state')
        const ADMIN_TENANT_ID = require('./src/state').ADMIN_TENANT_ID

        for (const sched of schedules) {
            if (sched.days && !sched.days.includes(currentDay)) continue
            const session = sessions.get(sched.tenant_id || ADMIN_TENANT_ID)
            if (!session?.sock || session.status !== 'authenticated') continue

            const schedKey = `sched_${sched.id}_${currentTime}`
            if (lastProactiveTime.get(schedKey)) continue
            lastProactiveTime.set(schedKey, Date.now())
            setTimeout(() => lastProactiveTime.delete(schedKey), 70000)

            try {
                let jid = sched.target_jid
                if (!jid.includes('@')) jid = jid.includes('-') ? `${jid}@g.us` : `${jid}@s.whatsapp.net`

                let message = sched.message
                if (sched.ai_generated && session.aiConfigs) {
                    const aiMsg = await getAIResponse(
                        `Escreva uma mensagem curta e natural para: "${sched.message}". Contexto: grupo do WhatsApp, tom descontraído.`,
                        session.aiConfigs
                    )
                    if (aiMsg) message = aiMsg
                }

                await sendSmartResponse(session.sock, jid, message, null, session.aiConfigs || {})
                console.log(`[SCHEDULE] ✅ "${sched.message?.substring(0,40)}" → ${jid}`)
            } catch (e) { console.error('[SCHEDULE] Erro:', e.message) }
        }
    } catch (err) { console.error('[SCHEDULE] Exceção:', err.message) }
}

// ── Start ──
const PORT = process.env.WHATSAPP_PORT || 3001
app.listen(PORT, () => {
    const border = '═'.repeat(70)
    console.log(`\n╔${border}╗`)
    console.log(`║${'  RED SYSTEM\'S WHATSAPP INTEGRATION MODULE  v' + VERSION .padEnd(70)}║`)
    console.log(`╠${border}╣`)
    console.log(`║${'  Modularizado em src/ — 15 módulos'.padEnd(70)}║`)
    console.log(`║${'  Changelog: ' + CHANGELOG .padEnd(70)}║`)
    console.log(`╠${border}╣`)
    console.log(`║${'  Porta: ' + PORT + ' | ' + new Date().toLocaleString('pt-BR') .padEnd(59)}║`)
    console.log(`╚${border}╝\n`)

    autoStartSavedSessions()

    // Loop de agendamentos
    setInterval(runScheduledMessages, 60000)
    console.log('[SCHEDULE] ⏰ Loop de agendamentos iniciado')
})
