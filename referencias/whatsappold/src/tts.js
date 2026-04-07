// ══════════════════════════════════════════════════
// TTS — Text-to-Speech (Edge-TTS + eSpeak)
// ══════════════════════════════════════════════════
const path = require('path')
const fs = require('fs')

const VALID_EDGE_VOICES_PTBR = [
    'pt-BR-FranciscaNeural',
    'pt-BR-AntonioNeural',
    'pt-BR-ThalitaMultilingualNeural',
]

const EDGE_VOICE_STYLE = {
    'pt-BR-FranciscaNeural':           { rate: '-5%', pitch: '+0Hz' },
    'pt-BR-AntonioNeural':             { rate: '-5%', pitch: '+0Hz' },
    'pt-BR-ThalitaMultilingualNeural': { rate:  '0%', pitch: '+0Hz' },
}

function cleanTextForTTS(text) {
    if (!text) return ''
    let c = text
    c = c.replace(/\b(k{2,}|ha(ha)+|rs(rs)*|lol+|hu(hu)+|he(he)+|ih+|ui+)\b/gi, '')
    c = c.replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\u{2300}-\u{23FF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{1FA00}-\u{1FAFF}]/gu, '')
    c = c.replace(/[\uFE0F\u200D\u20E3]/g, '')
    c = c.replace(/[*_~`]/g, '')
    c = c.replace(/https?:\/\/\S+/g, '')
    c = c.replace(/\s{2,}/g, ' ').trim()
    return c.substring(0, 500)
}

function textToSSML(text, voiceId, rate, pitch, volume) {
    const esc = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\.\s+/g, '. <break time="400ms"/> ')
        .replace(/\.\s*$/g, '. <break time="400ms"/>')
        .replace(/!\s*/g, '! <break time="350ms"/> ')
        .replace(/\?\s*/g, '? <break time="350ms"/> ')
        .replace(/\.\.\.\s*/g, '<break time="600ms"/> ')
        .replace(/,\s*/g, ', <break time="150ms"/> ')
        .replace(/;\s*/g, '; <break time="250ms"/> ')
        .replace(/—\s*/g, '<break time="300ms"/> ')

    return `<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='pt-BR'><voice name='${voiceId}'><prosody rate='${rate}' pitch='${pitch}' volume='${volume}'>${esc}</prosody></voice></speak>`
}

async function generateAudio(text, configs) {
    const ttsCfg = configs.tts || {}
    if (!(ttsCfg.enabled === true || ttsCfg.enabled === 'true')) return null

    const provider = ttsCfg.provider || 'edge'
    const cleanText = cleanTextForTTS(text)
    if (!cleanText) return null

    try {
        const { execFile } = require('child_process')
        const { promisify } = require('util')
        const execFileAsync = promisify(execFile)

        const tmpMp3 = path.join('/tmp', `tts_${Date.now()}.mp3`)
        const tmpWav = path.join('/tmp', `tts_${Date.now()}.wav`)
        const tmpOgg = path.join('/tmp', `tts_${Date.now() + 1}.ogg`)
        let generated = false

        if (provider === 'edge') {
            let voiceId = ttsCfg.voice_id || 'pt-BR-FranciscaNeural'
            if (!VALID_EDGE_VOICES_PTBR.includes(voiceId)) {
                console.warn(`[TTS] Voz "${voiceId}" obsoleta → pt-BR-FranciscaNeural`)
                voiceId = 'pt-BR-FranciscaNeural'
            }
            const voiceDefault = EDGE_VOICE_STYLE[voiceId] || { rate: '-5%', pitch: '+0Hz' }
            const ttsRate   = ttsCfg.rate   || voiceDefault.rate
            const ttsPitch  = ttsCfg.pitch  || voiceDefault.pitch
            const ttsVolume = ttsCfg.volume || '+0%'

            console.log(`[TTS] Edge-TTS → ${voiceId} | rate:${ttsRate} pitch:${ttsPitch} vol:${ttsVolume}`)

            const pyScript = `
import asyncio, sys, edge_tts
async def run():
    c = edge_tts.Communicate(
        text=sys.argv[1],
        voice=sys.argv[2],
        rate=sys.argv[3],
        pitch=sys.argv[4],
        volume=sys.argv[5]
    )
    await c.save(sys.argv[6])
asyncio.run(run())`.trim()

            const pyFile = path.join('/tmp', `tts_py_${Date.now()}.py`)
            fs.writeFileSync(pyFile, pyScript, 'utf8')

            try {
                await execFileAsync('python3', [
                    pyFile, cleanText, voiceId, ttsRate, ttsPitch, ttsVolume, tmpMp3
                ], { timeout: 25000 })
            } finally {
                try { fs.unlinkSync(pyFile) } catch (_) {}
            }

            if (fs.existsSync(tmpMp3)) {
                await execFileAsync('ffmpeg', ['-y', '-i', tmpMp3, '-c:a', 'libopus', '-b:a', '32k', '-vbr', 'on', tmpOgg], { timeout: 15000 })
                try { fs.unlinkSync(tmpMp3) } catch (_) {}
                generated = true
            }
        }

        if (provider === 'espeak') {
            try {
                await execFileAsync('espeak-ng', ['-v', 'pt-br', '-s', '155', '-p', '60', '-a', '180', '-w', tmpWav, cleanText], { timeout: 15000 })
                if (fs.existsSync(tmpWav)) {
                    await execFileAsync('ffmpeg', ['-y', '-i', tmpWav, '-c:a', 'libopus', '-b:a', '24k', '-vbr', 'on', tmpOgg], { timeout: 15000 })
                    try { fs.unlinkSync(tmpWav) } catch (_) {}
                    generated = true
                }
            } catch (err) { console.error('[TTS] espeak falhou:', err.message); return null }
        }

        if (!generated || !fs.existsSync(tmpOgg)) return null
        const audioBuffer = fs.readFileSync(tmpOgg)
        try { fs.unlinkSync(tmpOgg) } catch (_) {}
        console.log(`[TTS] ✅ ${audioBuffer.length} bytes via ${provider}`)
        return audioBuffer
    } catch (err) {
        console.error('[TTS] Exceção:', err.message)
        return null
    }
}

module.exports = {
    VALID_EDGE_VOICES_PTBR, EDGE_VOICE_STYLE,
    cleanTextForTTS, textToSSML, generateAudio
}
