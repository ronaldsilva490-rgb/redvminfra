const fs = require("fs");
const path = require("path");

function resolveDataDir() {
  return path.resolve(process.cwd(), process.env.REDIA_DATA_DIR || "./data");
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function dataPath(...parts) {
  const root = ensureDir(resolveDataDir());
  return path.join(root, ...parts);
}

function tmpPath(...parts) {
  return path.join(ensureDir(dataPath("tmp")), ...parts);
}

function authPath(...parts) {
  return path.join(ensureDir(dataPath("auth")), ...parts);
}

function dbPath() {
  return path.resolve(process.cwd(), process.env.REDIA_DB_PATH || dataPath("redia.sqlite"));
}

module.exports = { resolveDataDir, ensureDir, dataPath, tmpPath, authPath, dbPath };
