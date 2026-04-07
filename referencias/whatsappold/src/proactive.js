// ══════════════════════════════════════════════════
// PROACTIVE — LEARN + Realtime Proactive Analysis
// ══════════════════════════════════════════════════
const {
    supabase, sessions, conversationBuffers,
    lastProactiveTime, lastRealtimeAnalysis, realtimeInProgress,
    lastBotResponseByJid, LAST_BOT_RESPONSE_TTL,
    getCfg, DEFAULT_BUFFER_SIZE, DEFAULT_PROACTIVE_COOLDOWN, DEFAULT_REALTIME_COOLDOWN
} = require('./state')
const { getAIResponse } = require('./aiProvider')
const { sendSmartResponse } = require('./sender')
const { updateContextBuffer } = require('./context')
const { saveMemoryFact } = require('./memory')

async function learnFromConversation(tenantId, conversationId, newMessages, configs, isActiveGroup = false) {
    const learningCfg = configs.learning || {}
    if (learningCfg.enabled === false || learningCfg.enabled === 'false') return
    const analysisCfg = {
        ...configs,
        chat: {
            provider: learningCfg.provider || configs.proactive?.provider || 'groq',
            api_key: learningCfg.api_key || configs.proactive?.api_key || configs.api_key || '',
            model: learningCfg.model || configs.proactive?.model || ''
        }
    }

    const cooldownMs = getCfg(configs, 'proactive_cooldown_ms', DEFAULT_PROACTIVE_COOLDOWN)
    const cooldownKey = `learn_${tenantId}_${conversationId}`
    if (Date.now() - (lastProactiveTime.get(cooldownKey) || 0) < cooldownMs) return
    lastProactiveTime.set(cooldownKey, Date.now())

    try {
        const chatText = newMessages.map(m => `${m.author}: ${m.text}`).join('\n')
        const { data: existing } = await supabase.from('whatsapp_conversation_contexts')
            .select('summary, vibe').eq('tenant_id', tenantId).eq('conversation_id', conversationId).single()
        const oldSummary = existing?.summary || 'Nenhum'

        const contextPrompt = `CONVERSA RECENTE:\n${chatText}\n\nRESUMO ANTERIOR: ${oldSummary}\n\nRetorne APENAS este JSON (sem markdown):\n{"summary":"resumo atualizado máx 200 chars","vibe":"uma palavra p/ vibe (ex: Zoeira, Sério, Animado, Neutro, Polêmico)","group_type":"Amigos|Trabalho|Família|Geral","daily_topics":"temas do momento separados por vírgula","style":"gírias e expressões frequentes do grupo","context_hint":"dica curta relevante p/ próxima participação","profiles":[{"jid":"num@s.whatsapp.net","name":"Nome","nicknames":["apelido"],"memory_facts":["fato importante sobre esta pessoa"]}],"handoff_needed":false,"intent":""}`

        const ctxResponse = await getAIResponse(contextPrompt, analysisCfg, 'Analista de contexto conversacional. Responda APENAS com JSON puro.')
        let ctxResult = null
        if (ctxResponse) {
            try {
                const j = ctxResponse.replace(/```json\s*/gi, '').replace(/```/g, '').trim()
                const s = j.substring(j.indexOf('{'), j.lastIndexOf('}') + 1)
                ctxResult = JSON.parse(s)
            } catch (e) {
                console.warn('[LEARN] Parse de contexto falhou:', e.message)
                const mSummary = ctxResponse.match(/"summary"\s*:\s*"((?:[^"\\]|\\.)*)"/)?.[1] || ''
                const mVibe = ctxResponse.match(/"vibe"\s*:\s*"((?:[^"\\]|\\.)*)"/)?.[1] || 'Neutro'
                ctxResult = { summary: mSummary, vibe: mVibe }
            }
        }

        const chatCfg = configs.chat || {}
        const personality = chatCfg.system_prompt || 'Você é um membro humano do grupo.'

        const proactivePrompt = `${personality}\n\n[ANÁLISE INTERNA — NÃO ENVIE DIRETO, analise e decida]\nÚltimas mensagens:\n${chatText}\n\nDecida se deve enviar uma mensagem espontânea AGORA.\nRetorne APENAS este JSON (sem texto extra, sem markdown):\n{"thought":"mensagem curta natural se quiser participar, vazio se não","urgency":0,"trigger":""}\n\nRegras para "thought":\n- Máximo 2 frases curtas, linguagem natural do grupo\n- Use as gírias que aparecem na conversa\n- NUNCA comece com "Olá" ou saudações formais\n- Seja ousada: entre na conversa com mais frequência\n- Deixe VAZIO apenas se realmente não tiver NADA a acrescentar\nRegras para "urgency": número 0-10 (0=silêncio, 4+=vale participar, 8+=imperdível)\nRegras para "trigger": o que motivou (ex: "pergunta aberta", "piada", "polêmica") ou vazio`

        const proactiveResponse = await getAIResponse(proactivePrompt, analysisCfg, 'Responda APENAS com JSON puro de 3 campos.')
        let proResult = { thought: '', urgency: 0, trigger: '' }
        if (proactiveResponse) {
            try {
                const j = proactiveResponse.replace(/```json\s*/gi, '').replace(/```/g, '').trim()
                const s = j.substring(j.indexOf('{'), j.lastIndexOf('}') + 1)
                const parsed = JSON.parse(s)
                proResult = {
                    thought: (parsed.thought || parsed.proactive_thought || parsed.message || parsed.fala || '').trim(),
                    urgency: parseFloat(parsed.urgency || parsed.proactive_urgency || parsed.prioridade || 0),
                    trigger: parsed.trigger || parsed.proactive_trigger || parsed.motivo || '',
                }
            } catch (e) {
                console.warn('[LEARN] Parse proativo falhou:', e.message)
                const mThought = proactiveResponse.match(/"(?:thought|proactive_thought|message|fala)"\s*:\s*"((?:[^"\\]|\\.)*)"/i)?.[1] || ''
                const mUrgency = proactiveResponse.match(/"(?:urgency|proactive_urgency|prioridade)"\s*:\s*([0-9.]+)/i)?.[1] || '0'
                proResult = { thought: mThought.trim(), urgency: parseFloat(mUrgency), trigger: '' }
            }
        }

        console.log(`[LEARN] ✅ vibe:${ctxResult?.vibe || '?'} | urgency:${proResult.urgency} | thought:"${proResult.thought?.substring(0,50)}"`)

        updateContextBuffer(tenantId, conversationId, newMessages, ctxResult)

        if (ctxResult) {
            await supabase.from('whatsapp_conversation_contexts').upsert({
                tenant_id: tenantId, conversation_id: conversationId,
                summary: ctxResult.summary || oldSummary,
                vibe: ctxResult.vibe || 'Neutro',
                group_type: ctxResult.group_type || 'Geral',
                daily_topics: ctxResult.daily_topics || '',
                communication_style: ctxResult.style || '',
                context_hint: ctxResult.context_hint || '',
                updated_at: new Date()
            }, { onConflict: 'tenant_id, conversation_id' })

            if (ctxResult.profiles?.length) {
                for (const p of ctxResult.profiles) {
                    if (!p.jid) continue
                    const { data: existingProf } = await supabase
                        .from('whatsapp_contact_profiles')
                        .select('metadata').eq('tenant_id', tenantId).eq('contact_id', p.jid).single()

                    let meta = existingProf?.metadata || {}
                    if (!meta.nicknames) meta.nicknames = []
                    if (p.nicknames) p.nicknames.forEach(n => { if (n && !meta.nicknames.includes(n)) meta.nicknames.push(n) })

                    await supabase.from('whatsapp_contact_profiles').upsert({
                        tenant_id: tenantId, contact_id: p.jid,
                        full_name: p.name || null, nickname: meta.nicknames[0] || null,
                        metadata: meta, updated_at: new Date()
                    }, { onConflict: 'tenant_id, contact_id' })

                    if (p.memory_facts?.length) {
                        for (const fact of p.memory_facts) {
                            if (fact?.length > 5) await saveMemoryFact(tenantId, p.jid, fact)
                        }
                    }
                }
            }

            if (ctxResult.handoff_needed) {
                try {
                    await supabase.from('whatsapp_handoff_queue').upsert({
                        tenant_id: tenantId, conversation_id: conversationId,
                        reason: ctxResult.intent || 'Detectado pela IA', status: 'pending', created_at: new Date()
                    }, { onConflict: 'tenant_id, conversation_id' })
                } catch (_) {}
            }
        }

        // ── Disparo proativo (LEARN) ──
        const proactiveThought = proResult.thought
        const urgency          = proResult.urgency
        const proactiveCfg     = configs.proactive || {}
        const proactiveEnabled = proactiveCfg.enabled !== false && proactiveCfg.enabled !== 'false'
        const shouldParticipate = proactiveEnabled && proactiveThought.length > 1

        console.log(`[PROATIVO] urgency:${urgency} ativo:${isActiveGroup} thought:"${proactiveThought?.substring(0,40)}" → ${shouldParticipate ? '✅ processado' : '❌ vazio'}`)

        if (shouldParticipate) {
            const session = sessions.get(tenantId)
            if (session?.sock && session.status === 'authenticated') {
                const minDelay = urgency >= 8 ? 1000 : urgency >= 5 ? 2000 : 3500
                const maxDelay = urgency >= 8 ? 3000 : urgency >= 5 ? 6000 : 12000
                const delay    = minDelay + Math.random() * (maxDelay - minDelay)

                setTimeout(async () => {
                    try {
                        const lastSent = lastProactiveTime.get(`${tenantId}_${conversationId}`) || 0
                        if (Date.now() - lastSent < 4000) {
                            console.log(`[PROATIVO] ⏭️ Mensagem recente detectada, LEARN silenciado`)
                            return
                        }

                        const chatPersonalityPrompt = (configs.chat || {}).system_prompt || 'Você é um membro humano do grupo.'
                        const chatPrompt = `${chatPersonalityPrompt}\n[VOCÊ VAI PARTICIPAR ESPONTANEAMENTE DA CONVERSA]\n[INTENÇÃO: ${proactiveThought}]\n[ESTILO: natural, use gírias do grupo se houver, máx 2 frases, NUNCA comece com saudação formal, NUNCA mencione que é IA]\n\nEscreva SUA FALA para entrar na conversa agora:`

                        const learnResponse = await getAIResponse(chatPrompt, configs)
                        if (!learnResponse) return

                        const lastSentFinal = lastProactiveTime.get(`${tenantId}_${conversationId}`) || 0
                        if (Date.now() - lastSentFinal < 2000) {
                            console.log(`[PROATIVO] ⏭️ Outra resposta chegou durante geração LEARN, descartando`)
                            return
                        }

                        lastProactiveTime.set(`${tenantId}_${conversationId}`, Date.now())

                        const sessionLearn = sessions.get(tenantId)
                        if (!sessionLearn?.sock || sessionLearn.status !== 'authenticated') return

                        console.log(`[PROATIVO] ✅ Enviando: "${learnResponse.substring(0, 60)}"`)
                        await sendSmartResponse(sessionLearn.sock, conversationId, learnResponse, null, configs, { skipPresence: true })
                    } catch (e) {
                        console.error('[PROATIVO] Erro ao enviar:', e.message)
                    }
                }, delay)
            }
        }

    } catch (err) {
        console.error(`[LEARN] ❌ Erro:`, err.message)
    }
}

async function realtimeProactiveAnalysis(tenantId, conversationId, messageText, author, configs, sock, isActiveGroup) {
    const proactiveCfg = configs.proactive || {}
    if (proactiveCfg.enabled === false || proactiveCfg.enabled === 'false') return
    if (!messageText || messageText.length < 3) return

    const chatCfg = configs.chat || {}
    const apiKey  = chatCfg.api_key || configs.api_key || ''
    if (!apiKey) return

    const rtLockKey = `${tenantId}_${conversationId}`
    if (realtimeInProgress.has(rtLockKey)) {
        console.log(`[RT] ⏭️ Análise em andamento para ${conversationId}, pulando`)
        return
    }

    const rtKey      = `rt_${tenantId}_${conversationId}`
    const rtCooldown = getCfg(configs, 'realtime_cooldown_ms', DEFAULT_REALTIME_COOLDOWN)
    if (Date.now() - (lastRealtimeAnalysis.get(rtKey) || 0) < rtCooldown) return
    lastRealtimeAnalysis.set(rtKey, Date.now())

    const personality  = chatCfg.system_prompt || 'Voce e um membro humano do grupo.'
    const activeHint  = isActiveGroup
        ? 'O grupo esta MOVIMENTADO. Seja mais propensa a participar.'
        : 'So participe se for algo realmente relevante.'
    const frequency   = parseFloat(proactiveCfg.frequency || 0.15)

    realtimeInProgress.add(rtLockKey)

    try {
        const analysisPrompt = `${activeHint}\n\n${author} disse: "${messageText}"\n\nAnalise esta mensagem e retorne SOMENTE este JSON (sem markdown):\n{"should_reply":false,"urgency":0,"topic":"","angle":"","trigger":""}\n\n- should_reply: true se vale participar, false se nao\n- urgency: 0-10 (seja generoso — 4+ já vale participar se ativo, 6+ se ocioso)\n- topic: tema da mensagem em poucas palavras\n- angle: como a IA deve abordar\n- trigger: "pergunta","piada","polemica","nome_mencionado","celebracao" ou vazio`

        const analysisResponse = await getAIResponse(analysisPrompt, configs, 'Analista interno. Responda APENAS com JSON de 5 campos.')
        if (!analysisResponse) return

        const j = analysisResponse.replace(/```json\s*/gi, '').replace(/```/g, '').trim()
        const s = j.substring(j.indexOf('{'), j.lastIndexOf('}') + 1)
        let analysis
        try {
            analysis = JSON.parse(s)
        } catch (_) {
            const mR = analysisResponse.match(/"should_reply"\s*:\s*(true|false)/)?.[1]
            const mU = analysisResponse.match(/"urgency"\s*:\s*([0-9.]+)/)?.[1] || '0'
            const mT = analysisResponse.match(/"topic"\s*:\s*"((?:[^"\\]|\\.)*)"/)?.[1] || ''
            const mA = analysisResponse.match(/"angle"\s*:\s*"((?:[^"\\]|\\.)*)"/)?.[1] || ''
            analysis = { should_reply: mR === 'true', urgency: parseFloat(mU), topic: mT, angle: mA, trigger: '' }
        }

        const urgency  = parseFloat(analysis.urgency || 0)
        const topic    = (analysis.topic  || '').trim()
        const angle    = (analysis.angle  || '').trim()
        const trigger  = analysis.trigger || ''

        if (!analysis.should_reply || urgency < 1) return

        const urgencyThresh = isActiveGroup
            ? getCfg(configs, 'realtime_urgency_active', 3)
            : getCfg(configs, 'realtime_urgency_idle',   5)

        const roll          = Math.random()
        const effectiveFreq = isActiveGroup ? Math.min(frequency * 3.0, 0.90) : frequency * 1.5

        const shouldFire = urgency >= urgencyThresh && (
            urgency >= 9
            || (urgency >= 7 && roll < 0.92)
            || (urgency >= 5 && roll < effectiveFreq * 2.0)
            || (urgency >= 3 && roll < effectiveFreq)
            || roll < effectiveFreq * 0.5
        )

        console.log(`[RT] 📊 Análise | Author: ${author} | urgency: ${urgency} | roll: ${roll.toFixed(2)} | thresh: ${urgencyThresh} | ativo: ${isActiveGroup}`)
        console.log(`[RT] 📝 Topic: "${topic}" | Angle: "${angle}" | Trigger: "${trigger}" | Decisão: ${shouldFire ? '✅ VAI PARTICIPAR' : '❌ silêncio'}`)

        if (!shouldFire || !sock) return

        const proKey    = `${tenantId}_${conversationId}`
        lastProactiveTime.set(proKey, Date.now())

        const minDelay = urgency >= 8 ? 800  : urgency >= 5 ? 1500 : 3000
        const maxDelay = urgency >= 8 ? 2500 : urgency >= 5 ? 5000 : 10000
        const delay    = minDelay + Math.random() * (maxDelay - minDelay)

        setTimeout(async () => {
            try {
                const lastMain = lastProactiveTime.get(`${tenantId}_${conversationId}`) || 0
                if (Date.now() - lastMain < 3000) {
                    console.log(`[RT] ⏭️ Bot principal respondeu recentemente, RT silenciado`)
                    return
                }

                let convContext = ''
                try {
                    const { data: ctx } = await supabase
                        .from('whatsapp_conversation_contexts')
                        .select('vibe, style, context_hint')
                        .eq('tenant_id', tenantId).eq('conversation_id', conversationId).single()
                    if (ctx?.vibe)         convContext += `\n[VIBE DO GRUPO: ${ctx.vibe}]`
                    if (ctx?.style)        convContext += `\n[GÍRIAS DO GRUPO: ${ctx.style}]`
                    if (ctx?.context_hint) convContext += `\n[CONTEXTO: ${ctx.context_hint}]`
                } catch (_) {}

                let botResponseCtx = ''
                const lastResp = lastBotResponseByJid.get(`${tenantId}_${conversationId}`)
                if (lastResp && (Date.now() - lastResp.sentAt) < LAST_BOT_RESPONSE_TTL) {
                    botResponseCtx = `\n[ATENÇÃO: O BOT JÁ RESPONDEU ESSA CONVERSA AGORA HÁ POUCO: "${lastResp.text}"]\n[Sua participação deve COMPLEMENTAR isso — continue o raciocínio, adicione humor, reaja ao que foi dito, ou mude o ângulo. NUNCA repita nem contradiga.]`
                }

                const chatCfgRT = configs.chat || {}
                const personalityRT = chatCfgRT.system_prompt || personality

                const chatPrompt = `${personalityRT}${convContext}${botResponseCtx}\n[VOCÊ VAI PARTICIPAR ESPONTANEAMENTE DA CONVERSA]\n[TEMA: ${topic}]\n[ABORDAGEM: ${angle}]\n[${author} disse: "${messageText}"]\n[ESTILO: seja natural, use as gírias do grupo se houver, máx 2 frases, NUNCA comece com saudação formal, NUNCA mencione que é IA]\n\nEscreva SUA FALA para entrar na conversa agora:`

                const rtResponse = await getAIResponse(chatPrompt, configs)
                if (!rtResponse) return

                const lastMainFinal = lastProactiveTime.get(`${tenantId}_${conversationId}`) || 0
                if (Date.now() - lastMainFinal < 2000) {
                    console.log(`[RT] ⏭️ Resposta principal chegou durante geração RT, descartando`)
                    return
                }

                lastProactiveTime.set(`${tenantId}_${conversationId}`, Date.now())

                const sessionRT = sessions.get(tenantId)
                if (!sessionRT?.sock || sessionRT.status !== 'authenticated') return

                console.log(`[RT] ✅ Enviando proativo: "${rtResponse.substring(0, 60)}"`)
                await sendSmartResponse(sessionRT.sock, conversationId, rtResponse, null, configs, { skipPresence: true })
            } catch (e) {
                console.error('[RT] Erro ao gerar/enviar:', e.message)
            }
        }, delay)
    } catch (err) {
        console.error('[RT] Excecao:', err.message)
    } finally {
        realtimeInProgress.delete(rtLockKey)
    }
}

module.exports = { learnFromConversation, realtimeProactiveAnalysis }
