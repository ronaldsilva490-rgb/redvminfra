// ══════════════════════════════════════════════════
// STICKERS + REAÇÕES AUTOMÁTICAS
// ══════════════════════════════════════════════════
const path = require('path')
const fs = require('fs')

const STICKER_DIR = path.join(__dirname, '..', 'stickers')

const REACTION_MAP = {
    engraçado:  ['😂', '😆', '💀', '🤣'],
    positivo:   ['❤️', '🔥', '👏', '💪'],
    surpresa:   ['😮', '👀', '🤯', '😱'],
    concordo:   ['👍', '💯', '✅', '👌'],
    carinho:    ['❤️', '🥰', '💕', '😘'],
    triste:     ['😢', '🫂', '💙', '😔'],
    neutro:     ['👀', '🤔', '💬'],
}

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)] }

function pickReaction(vibe, text) {
    const t = (text || '').toLowerCase()
    if (/kkk|haha|rsrs|lol|😂|😆/.test(t))                    return pick(REACTION_MAP.engraçado)
    if (/boa|parab|feli|top|show|incrív|maneiro|demais/.test(t)) return pick(REACTION_MAP.positivo)
    if (/serio|sério|meus deus|que isso|caramba|oxe/.test(t))    return pick(REACTION_MAP.surpresa)
    if (/sim|claro|exato|concordo|verdade|isso aí/.test(t))      return pick(REACTION_MAP.concordo)
    if (/te amo|saudade|falta|amor|beijo/.test(t))               return pick(REACTION_MAP.carinho)
    if (/triste|choran|difícil|ruim|não consigo/.test(t))        return pick(REACTION_MAP.triste)
    if (/zoeira|piada|meme|kkk/.test(vibe?.toLowerCase() || '')) return pick(REACTION_MAP.engraçado)
    return Math.random() < 0.3 ? pick(REACTION_MAP.neutro) : null
}

async function sendReaction(sock, msg, emoji) {
    if (!emoji) return
    try {
        await sock.sendMessage(msg.key.remoteJid, {
            react: { text: emoji, key: msg.key }
        })
    } catch (e) {
        console.warn('[REACT] Falhou:', e.message)
    }
}

async function sendSticker(sock, remoteJid, mood) {
    if (!fs.existsSync(STICKER_DIR)) return
    try {
        const files = fs.readdirSync(STICKER_DIR).filter(f => {
            const lf = f.toLowerCase()
            if (mood === 'happy')   return lf.includes('happy') || lf.includes('feliz') || lf.includes('good')
            if (mood === 'love')    return lf.includes('love') || lf.includes('amor') || lf.includes('heart')
            if (mood === 'laugh')   return lf.includes('laugh') || lf.includes('rs') || lf.includes('lol')
            if (mood === 'wow')     return lf.includes('wow') || lf.includes('surpres') || lf.includes('omg')
            return true
        })
        if (!files.length) return
        const file = files[Math.floor(Math.random() * files.length)]
        const sticker = fs.readFileSync(path.join(STICKER_DIR, file))
        await sock.sendMessage(remoteJid, { sticker })
        console.log(`[STICKER] 🎭 Enviou ${file} (mood: ${mood})`)
    } catch (e) {
        console.warn('[STICKER] Falhou:', e.message)
    }
}

module.exports = {
    REACTION_MAP, pickReaction, sendReaction, sendSticker
}
