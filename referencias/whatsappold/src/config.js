// ══════════════════════════════════════════════════
// CONFIG — Carregamento de configurações (ai_config.json)
// ══════════════════════════════════════════════════
const path = require('path')
const fs = require('fs')
const { sessions, ADMIN_TENANT_ID } = require('./state')

const AI_CONFIG_PATH = path.join(__dirname, '..', 'ai_config.json')
let _aiConfigCache = null
let _aiConfigMtime = 0

function loadAIConfigFile() {
    try {
        const stat = fs.statSync(AI_CONFIG_PATH)
        const mtime = stat.mtimeMs
        if (_aiConfigCache && mtime === _aiConfigMtime) return _aiConfigCache
        const raw = fs.readFileSync(AI_CONFIG_PATH, 'utf8')
        _aiConfigCache = JSON.parse(raw)
        _aiConfigMtime = mtime
        console.log('[CONFIG] ✅ ai_config.json recarregado')
        return _aiConfigCache
    } catch (err) {
        console.error('[CONFIG] ❌ Erro ao ler ai_config.json:', err.message)
        return {}
    }
}

function invalidateConfigCache() {
    _aiConfigCache = null
    _aiConfigMtime = 0
}

async function loadTenantAIConfigs(tenantId) {
    try {
        const fileConfig = loadAIConfigFile()
        const d = fileConfig[tenantId] || fileConfig['admin'] || {}

        const chat      = d.chat      || {}
        const stt       = d.stt       || {}
        const vision    = d.vision    || {}
        const tts       = d.tts       || {}
        const learning  = d.learning  || {}
        const proactive = d.proactive || {}

        const configData = {
            tenant_id: tenantId,
            chat: {
                provider:       chat.provider       || '',
                api_key:        chat.api_key        || '',
                model:          chat.model          || '',
                system_prompt:  chat.system_prompt  || 'Você é um assistente.',
                red_instance_id: chat.red_instance_id || d.red_instance_id || '',
                red_proxy_url:  chat.red_proxy_url  || d.red_proxy_url || 'ws://redsystems.ddns.net:11434'
            },
            stt: {
                provider: stt.provider || '',
                api_key:  stt.api_key  || '',
                model:    stt.model    || '',
                enabled:  stt.enabled !== false && stt.enabled !== 'false'
            },
            vision: {
                provider: vision.provider || '',
                api_key:  vision.api_key  || '',
                model:    vision.model    || '',
                enabled:  vision.enabled !== false && vision.enabled !== 'false'
            },
            tts: {
                provider:          tts.provider         || 'edge',
                api_key:           tts.api_key          || '',
                model:             tts.model            || '',
                voice_id:          tts.voice_id         || 'pt-BR-AntonioNeural',
                enabled:           tts.enabled === true  || tts.enabled === 'true',
                audio_probability: parseFloat(tts.audio_probability) || 0.25,
                rate:              tts.rate   || '-5%',
                pitch:             tts.pitch  || '+0Hz',
                volume:            tts.volume || '+0%'
            },
            learning: {
                provider: learning.provider || '',
                api_key:  learning.api_key  || '',
                model:    learning.model    || '',
                enabled:  learning.enabled !== false && learning.enabled !== 'false'
            },
            proactive: {
                enabled:                 proactive.enabled !== false && proactive.enabled !== 'false',
                frequency:               parseFloat(proactive.frequency) || 0.15,
                provider:                proactive.provider || learning.provider || '',
                api_key:                 proactive.api_key  || learning.api_key  || '',
                model:                   proactive.model    || learning.model    || '',
                buffer_size:             parseInt(proactive.buffer_size)             || 6,
                proactive_cooldown_ms:   parseInt(proactive.proactive_cooldown_ms)   || 15000,
                realtime_cooldown_ms:    parseInt(proactive.realtime_cooldown_ms)    || 8000,
                activity_window_ms:      parseInt(proactive.activity_window_ms)      || 120000,
                active_group_thresh:     parseInt(proactive.active_group_thresh)     || 4,
                realtime_urgency_active: parseInt(proactive.realtime_urgency_active) || 3,
                realtime_urgency_idle:   parseInt(proactive.realtime_urgency_idle)   || 5,
                realtime_enabled:        proactive.realtime_enabled !== false && proactive.realtime_enabled !== 'false'
            },
            ai_provider:    chat.provider   || '',
            api_key:        chat.api_key    || '',
            model:          chat.model      || '',
            system_prompt:  chat.system_prompt || '',
            ai_prefix:      d.ai_prefix     || '',
            ai_bot_enabled: d.ai_bot_enabled !== false && d.ai_bot_enabled !== 'false',
            red_instance_id: chat.red_instance_id || d.red_instance_id || '',
            red_proxy_url:  d.red_proxy_url || 'ws://redsystems.ddns.net:11434'
        }

        const session = sessions.get(tenantId)
        if (session) {
            session.aiConfigs = configData
            const isRed = !!configData.chat?.red_instance_id
            const chatLabel = isRed ? `RED Claude (proxy) [${configData.chat.red_instance_id}]` : `${configData.chat.provider}/${configData.chat.model || '⚠️ SEM MODEL'}`
            console.log(`\n${'═'.repeat(60)}`)
            console.log(`[CONFIG] ✅ Tenant: ${tenantId}`)
            console.log(`[CONFIG] 💬 Chat     → ${chatLabel}`)
            console.log(`[CONFIG] 🎓 Learning → ${configData.learning.provider}/${configData.learning.model || '⚠️ SEM MODEL'} | enabled: ${configData.learning.enabled}`)
            console.log(`[CONFIG] 🚀 Proativo → ${configData.proactive.provider}/${configData.proactive.model || '⚠️ SEM MODEL'} | enabled: ${configData.proactive.enabled} | freq: ${configData.proactive.frequency}`)
            console.log(`[CONFIG] 🎙️  STT      → ${configData.stt.provider}/${configData.stt.model} | enabled: ${configData.stt.enabled}`)
            console.log(`[CONFIG] 👁️  Vision   → ${configData.vision.provider}/${configData.vision.model} | enabled: ${configData.vision.enabled}`)
            console.log(`[CONFIG] 🔊 TTS      → ${configData.tts.provider} | enabled: ${configData.tts.enabled}`)
            console.log(`[CONFIG] 🤖 Bot ativo: ${configData.ai_bot_enabled} | Prefix: "${configData.ai_prefix || '(nenhum)'}"`)
            console.log(`${'═'.repeat(60)}\n`)
        }
    } catch (err) {
        console.error(`Erro ao carregar configs [${tenantId}]:`, err?.message)
        const session = sessions.get(tenantId)
        if (session) session.aiConfigs = {
            chat: { provider: '', api_key: '', model: '', system_prompt: 'Você é um assistente.' },
            stt: { enabled: false }, vision: { enabled: false }, tts: { enabled: false },
            learning: { enabled: false }, proactive: { enabled: false }, ai_bot_enabled: false
        }
    }
}

module.exports = {
    AI_CONFIG_PATH, loadAIConfigFile, loadTenantAIConfigs, invalidateConfigCache
}
