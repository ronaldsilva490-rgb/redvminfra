(() => {
  if (window.__RED_IQ_LAB_BRIDGE_INSTALLED__) return;
  window.__RED_IQ_LAB_BRIDGE_INSTALLED__ = true;

  const SOURCE = "RED_IQ_LAB_BRIDGE";
  const liveSockets = [];

  const emit = (kind, payload) => {
    try {
      window.postMessage({ source: SOURCE, kind, payload }, "*");
    } catch (_) {}
  };

  const rememberSocket = (ws) => {
    liveSockets.push(ws);
    const forget = () => {
      const index = liveSockets.indexOf(ws);
      if (index >= 0) liveSockets.splice(index, 1);
    };
    ws.addEventListener("close", forget);
    ws.addEventListener("error", forget);
  };

  const patchWebSocket = () => {
    const OriginalWebSocket = window.WebSocket;
    if (!OriginalWebSocket || OriginalWebSocket.__redIqLabWrapped) return;

    function WrappedWebSocket(...args) {
      const ws = new OriginalWebSocket(...args);
      rememberSocket(ws);
      ws.addEventListener("message", (event) => {
        try {
          const text = typeof event.data === "string" ? event.data : "";
          if (text) emit("ws-message", text);
        } catch (_) {}
      });
      const originalSend = ws.send;
      ws.send = function (...sendArgs) {
        try {
          const text = typeof sendArgs[0] === "string" ? sendArgs[0] : "";
          if (text) emit("ws-send", text);
        } catch (_) {}
        return originalSend.apply(this, sendArgs);
      };
      return ws;
    }

    WrappedWebSocket.prototype = OriginalWebSocket.prototype;
    Object.setPrototypeOf(WrappedWebSocket, OriginalWebSocket);
    WrappedWebSocket.__redIqLabWrapped = true;
    window.WebSocket = WrappedWebSocket;
  };

  const patchCommandBridge = () => {
    if (window.__RED_IQ_LAB_BRIDGE_COMMANDS__) return;
    window.__RED_IQ_LAB_BRIDGE_COMMANDS__ = true;
    window.addEventListener("message", (event) => {
      if (event.source !== window) return;
      const data = event.data;
      if (!data || data.source !== SOURCE || data.kind !== "command") return;
      const command = String(data.payload?.command || "");
      const id = String(data.payload?.id || "");
      if (!command || !id) return;

      if (command === "ws-send") {
        const text = String(data.payload?.payload?.text || "");
        const socket = [...liveSockets].reverse().find((item) => item && item.readyState === 1);
        if (!socket) {
          emit("command-result", { id, command, ok: false, error: "no_live_socket" });
          return;
        }
        try {
          socket.send(text);
          emit("command-result", {
            id,
            command,
            ok: true,
            result: { sent: true, length: text.length },
          });
        } catch (error) {
          emit("command-result", { id, command, ok: false, error: String(error) });
        }
        return;
      }

      if (command === "eval-main") {
        const code = String(data.payload?.payload?.code || "");
        try {
          const value = Function(`"use strict"; return (${code});`)();
          emit("command-result", {
            id,
            command,
            ok: true,
            result: { value },
          });
        } catch (error1) {
          try {
            const value = Function(String(code))();
            emit("command-result", {
              id,
              command,
              ok: true,
              result: { value },
            });
          } catch (error2) {
            emit("command-result", {
              id,
              command,
              ok: false,
              error: String(error2 || error1),
            });
          }
        }
      }
    });
  };

  patchWebSocket();
  patchCommandBridge();
})();
