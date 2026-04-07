require("dotenv").config();

const store = require("./store");
const dashboard = require("./dashboard");
const whatsapp = require("./whatsapp");

async function main() {
  store.initStore();
  const config = store.getConfig();
  dashboard.startDashboard({ whatsapp });
  if (config.whatsapp?.auto_start) {
    whatsapp.startWhatsApp(config).catch((err) => {
      console.warn("[whatsapp] auto-start failed:", err.message);
    });
  }
  console.log("[redia] started");
}

process.on("uncaughtException", (err) => {
  console.error("[fatal] uncaughtException:", err);
});

process.on("unhandledRejection", (err) => {
  console.error("[fatal] unhandledRejection:", err);
});

main().catch((err) => {
  console.error("[redia] failed:", err);
  process.exitCode = 1;
});
