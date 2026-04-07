const fs = require("fs");
const { execFile } = require("child_process");
const { promisify } = require("util");
const { tmpPath } = require("./paths");

const execFileAsync = promisify(execFile);

const EDGE_VOICES_PTBR = new Set([
  "pt-BR-FranciscaNeural",
  "pt-BR-AntonioNeural",
  "pt-BR-ThalitaMultilingualNeural",
]);

function cleanTextForTts(text, maxChars = 520) {
  return String(text || "")
    .replace(/\b(k{2,}|ha(ha)+|rs(rs)*|lol+|hu(hu)+|he(he)+)\b/gi, "")
    .replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\u{FE00}-\u{FE0F}]/gu, "")
    .replace(/[*_~`#>\[\]]/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s{2,}/g, " ")
    .trim()
    .slice(0, maxChars);
}

function shouldSendAudio(config, text) {
  const cfg = config.tts || {};
  if (!cfg.enabled) return false;
  const clean = cleanTextForTts(text, cfg.max_chars || 520);
  if (clean.length < 8 || clean.length > (cfg.max_chars || 520)) return false;
  const probability = Math.max(0, Math.min(1, Number(cfg.audio_probability || 0)));
  return Math.random() < probability;
}

async function generateEdgeTts(text, config) {
  const cfg = config.tts || {};
  const clean = cleanTextForTts(text, cfg.max_chars || 520);
  if (!clean) return null;

  const voice = EDGE_VOICES_PTBR.has(cfg.voice) ? cfg.voice : "pt-BR-FranciscaNeural";
  const rate = cfg.rate || "-5%";
  const pitch = cfg.pitch || "+0Hz";
  const volume = cfg.volume || "+0%";
  const stamp = `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const pyFile = tmpPath(`edge_tts_${stamp}.py`);
  const mp3File = tmpPath(`edge_tts_${stamp}.mp3`);
  const oggFile = tmpPath(`edge_tts_${stamp}.ogg`);
  const py = `
import asyncio, sys, edge_tts
async def run():
    communicator = edge_tts.Communicate(
        text=sys.argv[1],
        voice=sys.argv[2],
        rate=sys.argv[3],
        pitch=sys.argv[4],
        volume=sys.argv[5],
    )
    await communicator.save(sys.argv[6])
asyncio.run(run())
`.trim();

  try {
    fs.writeFileSync(pyFile, py, "utf8");
    await execFileAsync("python3", [pyFile, clean, voice, rate, pitch, volume, mp3File], { timeout: 30000 });
    await execFileAsync("ffmpeg", ["-y", "-i", mp3File, "-c:a", "libopus", "-b:a", "32k", "-vbr", "on", oggFile], { timeout: 20000 });
    return fs.readFileSync(oggFile);
  } finally {
    for (const file of [pyFile, mp3File, oggFile]) {
      try {
        if (fs.existsSync(file)) fs.unlinkSync(file);
      } catch {
        // ignore tmp cleanup
      }
    }
  }
}

module.exports = { cleanTextForTts, shouldSendAudio, generateEdgeTts };
