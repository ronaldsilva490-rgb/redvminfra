// ══════════════════════════════════════════════════
// MEMORY — Memória de longo prazo (Supabase)
// ══════════════════════════════════════════════════
const { supabase } = require('./state')

async function saveMemoryFact(tenantId, contactJid, fact, category = 'geral') {
    try {
        await supabase.from('whatsapp_long_term_memory').insert({
            tenant_id: tenantId, contact_jid: contactJid,
            fact, category, created_at: new Date()
        })
    } catch (_) {}
}

async function getContactMemory(tenantId, contactJid, limit = 10) {
    try {
        const { data } = await supabase
            .from('whatsapp_long_term_memory')
            .select('fact, category, created_at')
            .eq('tenant_id', tenantId).eq('contact_jid', contactJid)
            .order('created_at', { ascending: false }).limit(limit)
        if (!data?.length) return ''
        return '\n[MEMÓRIA DE LONGO PRAZO:\n' + data.map(d => `• ${d.fact}`).join('\n') + ']'
    } catch (_) { return '' }
}

module.exports = { saveMemoryFact, getContactMemory }
