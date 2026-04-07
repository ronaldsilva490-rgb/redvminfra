// ══════════════════════════════════════════════════
// CONTEXT — Contexto de conversa, empresa, nomes, buffer
// ══════════════════════════════════════════════════
const {
    supabase, ADMIN_TENANT_ID,
    contextBuffer, CONTEXT_BUFFER_MAX_MSGS, CONTEXT_BUFFER_TTL_MS
} = require('./state')

function updateContextBuffer(tenantId, conversationId, messages, learnResult) {
    const key = `${tenantId}_${conversationId}`
    const existing = contextBuffer.get(key) || { messages: [] }
    const allMsgs = [...(existing.messages || []), ...messages]
    const trimmed = allMsgs.slice(-CONTEXT_BUFFER_MAX_MSGS)
    contextBuffer.set(key, {
        messages:  trimmed,
        summary:   learnResult?.summary      || existing.summary  || '',
        vibe:      learnResult?.vibe         || existing.vibe     || 'Neutro',
        topics:    learnResult?.daily_topics || existing.topics   || '',
        style:     learnResult?.style        || existing.style    || '',
        hint:      learnResult?.context_hint || existing.hint     || '',
        updatedAt: Date.now()
    })
    console.log(`[CTX-BUFFER] 📝 Atualizado ${key} | msgs: ${trimmed.length} | vibe: ${learnResult?.vibe || existing.vibe || '?'}`)
}

/**
 * Adiciona uma única mensagem ao buffer de contexto imediatamente.
 * Garante que a história recente esteja sempre up-to-date para a IA.
 */
function appendMessageToContextBuffer(tenantId, conversationId, author, text) {
    const key = `${tenantId}_${conversationId}`
    const existing = contextBuffer.get(key) || { 
        messages: [], summary: '', vibe: 'Neutro', topics: '', style: '', hint: '', updatedAt: 0 
    }
    
    // Evita duplicatas se a mesma mensagem for processada duas vezes
    const isDup = existing.messages.some(m => m.author === author && m.text === text && (Date.now() - (existing.updatedAt || 0) < 2000))
    if (isDup) return

    const newMessage = { author, text, timestamp: Date.now() }
    const allMsgs = [...(existing.messages || []), newMessage]
    const trimmed = allMsgs.slice(-CONTEXT_BUFFER_MAX_MSGS)
    
    contextBuffer.set(key, {
        ...existing,
        messages: trimmed,
        updatedAt: Date.now()
    })
}

function buildContextBlock(tenantId, conversationId) {
    const key = `${tenantId}_${conversationId}`
    const ctx = contextBuffer.get(key)
    if (!ctx) return ''
    if (Date.now() - (ctx.updatedAt || 0) > CONTEXT_BUFFER_TTL_MS) {
        contextBuffer.delete(key)
        return ''
    }
    let block = '\n[CONTEXTO RECENTE DA CONVERSA:'
    if (ctx.vibe)    block += `\n• Vibe atual: ${ctx.vibe}`
    if (ctx.topics)  block += `\n• Tópicos: ${ctx.topics}`
    if (ctx.style)   block += `\n• Estilo/gírias: ${ctx.style}`
    if (ctx.hint)    block += `\n• Dica: ${ctx.hint}`
    if (ctx.summary) block += `\n• Resumo: ${ctx.summary}`
    if (ctx.messages?.length) {
        block += `\n• Últimas mensagens:\n`
        block += ctx.messages.slice(-10).map(m => `  ${m.author}: ${m.text}`).join('\n')
    }
    block += '\n]'
    return block
}

async function resolveNames(text, tenantId, sock) {
    if (!text) return text
    const jidRegex = /(@\d+|@[\w.-]+(@g\.us|@s\.whatsapp\.net|@lid))/g
    const matches = text.match(jidRegex) || []
    let resolvedText = text
    for (const jid of matches) {
        let cleanJid = jid.startsWith('@') ? jid.substring(1) : jid
        if (!cleanJid.includes('@')) cleanJid = cleanJid + (cleanJid.includes('-') ? '@g.us' : '@s.whatsapp.net')
        try {
            let name = null
            if (cleanJid.endsWith('@g.us')) {
                const meta = await sock.groupMetadata(cleanJid).catch(() => null)
                name = meta?.subject
            } else {
                const { data: contact } = await supabase.from('whatsapp_contact_profiles')
                    .select('full_name, nickname').eq('tenant_id', tenantId).eq('contact_id', cleanJid).single()
                name = contact?.nickname || contact?.full_name
            }
            if (name) resolvedText = resolvedText.replace(jid, `@${name}`)
        } catch (_) {}
    }
    return resolvedText
}

async function getTenantContext(tenantId) {
    if (tenantId === ADMIN_TENANT_ID) return ''
    try {
        const { data: tenant } = await supabase.from('tenants').select('nome, descricao, tipo, endereco, cidade').eq('id', tenantId).single()
        const { data: products } = await supabase.from('products').select('nome, preco, estoque_atual').eq('tenant_id', tenantId).limit(20)
        let ctx = `Empresa: ${tenant?.nome || 'Empresa'}\nRamo: ${tenant?.tipo || 'Comércio'}\nDescrição: ${tenant?.descricao || ''}\nEndereço: ${tenant?.endereco || ''}, ${tenant?.cidade || ''}\n`
        if (products?.length) {
            ctx += '\nPRODUTOS:\n'
            products.forEach(p => { ctx += `- ${p.nome}: R$ ${p.preco?.toFixed(2) || 'Sob consulta'} (Estoque: ${p.estoque_atual || 'N/A'})\n` })
        }
        return ctx
    } catch (err) { return '' }
}

async function getGroupPersonality(tenantId, groupJid) {
    try {
        const { data } = await supabase
            .from('whatsapp_group_configs')
            .select('system_prompt, personality_name, enabled')
            .eq('tenant_id', tenantId).eq('group_jid', groupJid).single()
        return data || null
    } catch (_) { return null }
}

function detectSimpleIntent(text) {
    const { normalize } = require('./state')
    const t = normalize(text)
    if (/qual.*(preco|valor|custa|quanto)/.test(t) || /preco|valor custa|quanto e/.test(t)) return 'pergunta_preco'
    if (/que horas|horario|abre|fecha|funcionamento/.test(t)) return 'pergunta_horario'
    if (/onde fica|endereco|localizacao|como chegar/.test(t)) return 'pergunta_endereco'
    if (/whatsapp|zap|telefone|contato|numero/.test(t)) return 'pergunta_contato'
    return null
}

module.exports = {
    updateContextBuffer, appendMessageToContextBuffer, buildContextBlock,
    resolveNames, getTenantContext, getGroupPersonality, detectSimpleIntent
}
