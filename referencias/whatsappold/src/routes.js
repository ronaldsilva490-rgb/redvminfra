// ══════════════════════════════════════════════════
// ROUTES — API Express endpoints
// ══════════════════════════════════════════════════
const path = require('path')
const fs = require('fs')
const { supabase, sessions, ADMIN_TENANT_ID } = require('./state')
const { AI_CONFIG_PATH, loadAIConfigFile, loadTenantAIConfigs, invalidateConfigCache } = require('./config')
const { connectToWhatsApp } = require('./connection')
const { appendMessageToContextBuffer } = require('./context')

function setupRoutes(app) {
    // ── Redirects de conveniência ──
    app.get('/status',   (_, res) => res.redirect('/status/admin'))
    app.post('/start',   (_, res) => res.redirect(307, '/start/admin'))
    app.post('/stop',    (_, res) => res.redirect(307, '/stop/admin'))
    app.get('/groups',   (_, res) => res.redirect('/groups/admin'))
    app.post('/send',    (_, res) => res.redirect(307, '/send/admin'))
    app.post('/reset',   (_, res) => res.redirect(307, '/reset/admin'))
    app.post('/ai/reload', async (_, res) => { await loadTenantAIConfigs(ADMIN_TENANT_ID); res.json({ success: true }) })

    app.post('/ai/config/reload', (_, res) => {
        invalidateConfigCache()
        const cfg = loadAIConfigFile()
        for (const [tid] of sessions) loadTenantAIConfigs(tid).catch(() => {})
        res.json({ success: true, tenants: Object.keys(cfg) })
    })

    app.put('/ai/config/:tenantId', (req, res) => {
        try {
            const { tenantId } = req.params
            const body = req.body || {}
            let cfg = {}
            try { const raw = fs.readFileSync(AI_CONFIG_PATH, 'utf8'); cfg = JSON.parse(raw) } catch (_) {}
            const existing = cfg[tenantId] || cfg['admin'] || {}

            const mergeSection = (sectionName, existingSection, newSection) => {
                if (!newSection || typeof newSection !== 'object') return existingSection
                const merged = { ...existingSection, ...newSection }
                if (newSection.api_key && (newSection.api_key.includes('***') || newSection.api_key.trim() === '')) {
                    merged.api_key = existingSection.api_key
                } else if (newSection.api_key) {
                    merged.api_key = newSection.api_key.trim()
                }
                return merged
            }

            const chatBase = existing.chat || {}
            const newChat = body.chat || {}
            if (body.ai_provider) newChat.provider = body.ai_provider
            if (body.api_key) newChat.api_key = body.api_key
            if (body.model) newChat.model = body.model
            if (body.system_prompt) newChat.system_prompt = body.system_prompt
            if (body.red_instance_id) newChat.red_instance_id = body.red_instance_id

            cfg[tenantId] = {
                ...existing,
                ai_bot_enabled: body.ai_enabled ?? body.ai_bot_enabled ?? existing.ai_bot_enabled ?? true,
                ai_prefix:      body.ai_prefix ?? existing.ai_prefix ?? '',
                red_instance_id: body.red_instance_id ?? existing.red_instance_id ?? '',
                red_proxy_url:  body.red_proxy_url ?? existing.red_proxy_url ?? 'ws://redsystems.ddns.net:11434',
                chat:     mergeSection('chat', existing.chat || {}, newChat),
                stt:      mergeSection('stt', existing.stt || {}, body.stt || {}),
                vision:   mergeSection('vision', existing.vision || {}, body.vision || {}),
                tts:      mergeSection('tts', existing.tts || {}, body.tts || {}),
                learning: mergeSection('learning', existing.learning || {}, body.learning || {}),
                proactive:mergeSection('proactive', existing.proactive || {}, body.proactive || {}),
            }

            fs.writeFileSync(AI_CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf8')
            invalidateConfigCache()
            loadTenantAIConfigs(tenantId).catch(() => {})
            res.json({ success: true })
        } catch (err) {
            res.status(500).json({ success: false, error: err.message })
        }
    })

    app.get('/ai/config', (_, res) => {
        const cfg = loadAIConfigFile()
        const safe = JSON.parse(JSON.stringify(cfg))
        for (const t of Object.values(safe)) {
            for (const section of Object.values(t)) {
                if (section && typeof section === 'object' && section.api_key) section.api_key = section.api_key ? '***' : ''
            }
        }
        res.json(safe)
    })

    app.get('/status/:tenantId', (req, res) => {
        const s = sessions.get(req.params.tenantId)
        if (!s) return res.json({ status: 'disconnected', qr: null })
        res.json({ status: s.status, qr: s.lastQr })
    })

    app.post('/start/:tenantId', async (req, res) => {
        try {
            const { tenantId } = req.params
            const existing = sessions.get(tenantId)
            if (existing && existing.status !== 'disconnected' && existing.status !== 'error')
                return res.json({ success: true, message: 'Sessão já ativa.', status: existing.status })
            const authPath = path.join(__dirname, '..', `auth_info_baileys/tenant_${tenantId}`)
            let forceReset = false
            if (fs.existsSync(authPath) && !fs.existsSync(path.join(authPath, 'creds.json'))) {
                fs.rmSync(authPath, { recursive: true, force: true }); forceReset = true
            }
            res.json({ success: true, message: 'Iniciando...', status: 'connecting' })
            connectToWhatsApp(tenantId, forceReset).catch(err => console.error(`[BG] Falha:`, err))
        } catch (err) { if (!res.headersSent) res.status(500).json({ success: false, error: err.message }) }
    })

    app.post('/stop/:tenantId', async (req, res) => {
        const { tenantId } = req.params
        const session = sessions.get(tenantId)
        const authPath = path.join(__dirname, '..', `auth_info_baileys/tenant_${tenantId}`)
        if (session?.sock) {
            try { await session.sock.logout(); res.json({ success: true }) }
            catch (e) { sessions.delete(tenantId); if (fs.existsSync(authPath)) fs.rmSync(authPath, { recursive: true, force: true }); res.json({ success: true }) }
        } else {
            if (fs.existsSync(authPath)) fs.rmSync(authPath, { recursive: true, force: true })
            res.json({ success: true })
        }
    })

    app.post('/reset/:tenantId', async (req, res) => {
        const { tenantId } = req.params
        const session = sessions.get(tenantId)
        if (session?.sock) { try { session.sock.end() } catch (_) {} }
        sessions.delete(tenantId)
        const authPath = path.join(__dirname, '..', `auth_info_baileys/tenant_${tenantId}`)
        if (fs.existsSync(authPath)) fs.rmSync(authPath, { recursive: true, force: true })
        try { await supabase.from('whatsapp_sessions').delete().eq('tenant_id', tenantId) } catch (_) {}
        res.json({ success: true, message: 'Sessão resetada.' })
    })

    app.post('/ai/reload/:tenantId', async (req, res) => { await loadTenantAIConfigs(req.params.tenantId); res.json({ success: true }) })

    app.post('/ai/list-models', async (req, res) => {
        const { api_key, provider } = req.body
        if (!api_key || !provider) return res.status(400).json({ error: 'api_key e provider obrigatórios' })
        try {
            let apiUrl = '', headers = {}
            if (provider === 'gemini')           apiUrl = `https://generativelanguage.googleapis.com/v1beta/models?key=${api_key}`
            else if (provider === 'groq')        { apiUrl = 'https://api.groq.com/openai/v1/models'; headers = { Authorization: `Bearer ${api_key}` } }
            else if (provider === 'openrouter')  { apiUrl = 'https://openrouter.ai/api/v1/models'; headers = { Authorization: `Bearer ${api_key}` } }
            else if (provider === 'nvidia')      { apiUrl = 'https://integrate.api.nvidia.com/v1/models'; headers = { Authorization: `Bearer ${api_key}` } }
            else if (provider === 'openai')      { apiUrl = 'https://api.openai.com/v1/models'; headers = { Authorization: `Bearer ${api_key}` } }
            else if (provider === 'kimi' || provider === 'moonshot') { apiUrl = 'https://api.moonshot.ai/v1/models'; headers = { Authorization: `Bearer ${api_key}` } }
            else if (provider === 'deepseek')    { apiUrl = 'https://api.deepseek.com/v1/models'; headers = { Authorization: `Bearer ${api_key}` } }
            else if (provider === 'ollama') {
                const ollamaUrl = process.env.OLLAMA_PROXY_URL || 'http://localhost:11434'
                try { const r = await fetch(`${ollamaUrl}/api/tags`); const d = await r.json(); return res.json({ success: true, models: (d.models || []).map(m => ({ id: m.name, name: m.name })) }) }
                catch (e) { return res.status(500).json({ error: `Ollama offline: ${e.message}` }) }
            } else return res.status(400).json({ error: 'Provider inválido' })
            const response = await fetch(apiUrl, { headers })
            const data = await response.json()
            if (data.error) throw new Error(data.error.message || 'Erro ao buscar modelos')
            let models = []
            if (provider === 'gemini') models = (data.models || []).filter(m => m.supportedGenerationMethods?.includes('generateContent')).map(m => ({ id: m.name.replace('models/', ''), name: m.displayName || m.name.replace('models/', '') }))
            else models = (data.data || []).map(m => ({ id: m.id, name: m.id }))
            res.json({ success: true, models })
        } catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.get('/groups/:tenantId', async (req, res) => {
        const session = sessions.get(req.params.tenantId)
        if (!session || session.status !== 'authenticated') return res.status(503).json({ success: false, error: 'Não conectado' })
        try {
            const groupMetadata = await session.sock.groupFetchAllParticipating()
            res.json({ success: true, groups: Object.values(groupMetadata).map(g => ({ id: g.id, subject: g.subject })) })
        } catch (err) { res.status(500).json({ success: false, error: err.message }) }
    })

    app.post('/send/:tenantId', async (req, res) => {
        const { tenantId } = req.params
        const session = sessions.get(tenantId)
        if (!session || session.status !== 'authenticated') return res.status(503).json({ success: false, error: 'Não conectado' })
        try {
            const { number, message } = req.body
            if (!number || !message) return res.status(400).json({ error: 'number e message obrigatórios' })
            let jid = number
            if (!jid.includes('@')) jid = (jid.includes('-') || jid.length > 15) ? `${jid}@g.us` : `${jid}@s.whatsapp.net`
            await session.sock.sendMessage(jid, { text: message })
            appendMessageToContextBuffer(tenantId, jid, 'Você (Bot)', message)
            res.json({ success: true })
        } catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.get('/schedules', async (_, res) => {
        try { const { data } = await supabase.from('whatsapp_schedules').select('*').order('send_time'); res.json({ success: true, schedules: data || [] }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.post('/schedules', async (req, res) => {
        try { const { data, error } = await supabase.from('whatsapp_schedules').insert(req.body).select().single(); if (error) throw error; res.json({ success: true, schedule: data }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.delete('/schedules/:id', async (req, res) => {
        try { await supabase.from('whatsapp_schedules').delete().eq('id', req.params.id); res.json({ success: true }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.get('/group-configs/:tenantId', async (req, res) => {
        try { const { data } = await supabase.from('whatsapp_group_configs').select('*').eq('tenant_id', req.params.tenantId); res.json({ success: true, configs: data || [] }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.post('/group-configs', async (req, res) => {
        try { const { data, error } = await supabase.from('whatsapp_group_configs').upsert(req.body, { onConflict: 'tenant_id, group_jid' }).select().single(); if (error) throw error; res.json({ success: true, config: data }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.get('/handoff', async (_, res) => {
        try { const { data } = await supabase.from('whatsapp_handoff_queue').select('*').eq('status', 'pending').order('created_at', { ascending: false }); res.json({ success: true, queue: data || [] }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.post('/handoff/:id/resolve', async (req, res) => {
        try { await supabase.from('whatsapp_handoff_queue').update({ status: 'resolved', resolved_at: new Date() }).eq('id', req.params.id); res.json({ success: true }) }
        catch (err) { res.status(500).json({ error: err.message }) }
    })

    app.get('/memory/:tenantId/:contactJid', async (req, res) => {
        try {
            const { data } = await supabase.from('whatsapp_long_term_memory')
                .select('*').eq('tenant_id', req.params.tenantId).eq('contact_jid', req.params.contactJid)
                .order('created_at', { ascending: false }).limit(30)
            res.json({ success: true, memories: data || [] })
        } catch (err) { res.status(500).json({ error: err.message }) }
    })
}

module.exports = { setupRoutes }
