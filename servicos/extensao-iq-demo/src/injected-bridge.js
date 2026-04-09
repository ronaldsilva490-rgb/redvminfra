(() => {
  if (window.__RED_IQ_BRIDGE_INSTALLED__) return;
  window.__RED_IQ_BRIDGE_INSTALLED__ = true;

  const SOURCE = "RED_IQ_BRIDGE";
  const liveSockets = [];
  const shouldCapture = (text) => /iqoption|option|openets|billing|profile|balance|practice|demo|binary|binaria|digital|blitz|otc|asset|instrument|active|quote|price|profit|countdown|expiration/i.test(String(text || ""));
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
    if (!OriginalWebSocket || OriginalWebSocket.__redIqWrapped) return;

    function WrappedWebSocket(...args) {
      const ws = new OriginalWebSocket(...args);
      rememberSocket(ws);
      try {
        emit("ws-open", { url: String(args[0] || "") });
      } catch (_) {}
      const originalSend = ws.send;
      ws.send = function (...sendArgs) {
        try {
          const text = typeof sendArgs[0] === "string" ? sendArgs[0] : "";
          if (text) emit("ws-send", text);
        } catch (_) {}
        return originalSend.apply(this, sendArgs);
      };
      ws.addEventListener("message", (event) => {
        try {
          const text = typeof event.data === "string" ? event.data : "";
          if (text) {
            emit("ws-message", text);
          }
        } catch (_) {}
      });
      return ws;
    }

    WrappedWebSocket.prototype = OriginalWebSocket.prototype;
    Object.setPrototypeOf(WrappedWebSocket, OriginalWebSocket);
    WrappedWebSocket.__redIqWrapped = true;
    window.WebSocket = WrappedWebSocket;
  };

  const patchCommandBridge = () => {
    if (window.__RED_IQ_BRIDGE_COMMANDS__) return;
    window.__RED_IQ_BRIDGE_COMMANDS__ = true;
    window.addEventListener("message", (event) => {
      if (event.source !== window) return;
      const data = event.data;
      if (!data || data.source !== SOURCE || data.kind !== "command") return;
      const command = String(data.payload?.command || "");
      const id = String(data.payload?.id || "");
      if (!command || !id) return;

      if (command === "ws-send") {
        const text = String(data.payload?.payload?.text || data.payload?.text || "");
        const socket = [...liveSockets].reverse().find((item) => item && item.readyState === 1);
        if (!socket) {
          emit("ws-command-result", { id, command, ok: false, error: "no_live_socket" });
          return;
        }
        try {
          socket.send(text);
          emit("ws-command-result", {
            id,
            command,
            ok: true,
            result: {
              sent: true,
              length: text.length,
            },
          });
        } catch (error) {
          emit("ws-command-result", {
            id,
            command,
            ok: false,
            error: String(error),
          });
        }
      }
    });
  };

  const patchFetch = () => {
    const originalFetch = window.fetch;
    if (!originalFetch || originalFetch.__redIqWrapped) return;

    const wrappedFetch = async function (...args) {
      const response = await originalFetch.apply(this, args);
      try {
        const url = String(args[0]?.url || args[0] || "");
        if (shouldCapture(url)) {
          let text = "";
          try {
            const cloned = response.clone();
            text = await cloned.text();
          } catch (_) {}
          emit("fetch", {
            url,
            status: response.status,
            text: text.slice(0, 2000),
          });
        }
      } catch (_) {}
      return response;
    };

    wrappedFetch.__redIqWrapped = true;
    window.fetch = wrappedFetch;
  };

  const patchXhr = () => {
    const proto = window.XMLHttpRequest?.prototype;
    if (!proto || proto.__redIqWrapped) return;

    const open = proto.open;
    const send = proto.send;

    proto.open = function (method, url, ...rest) {
      this.__redIqUrl = String(url || "");
      this.__redIqMethod = String(method || "");
      return open.call(this, method, url, ...rest);
    };

    proto.send = function (...args) {
      this.addEventListener("load", function () {
        try {
          const url = String(this.__redIqUrl || "");
          const text = typeof this.responseText === "string" ? this.responseText.slice(0, 2000) : "";
          if (shouldCapture(url) || text) {
            emit("xhr", {
              url,
              method: this.__redIqMethod || "",
              status: this.status,
              text,
            });
          }
        } catch (_) {}
      });
      return send.apply(this, args);
    };

    proto.__redIqWrapped = true;
  };

  const patchCanvasText = () => {
    const proto = window.CanvasRenderingContext2D?.prototype;
    if (!proto || proto.__redIqCanvasWrapped) return;

    const wrap = (methodName) => {
      const original = proto[methodName];
      if (typeof original !== "function") return;
      proto[methodName] = function (text, ...rest) {
        try {
          const value = String(text || "");
          if (shouldCapture(value)) {
            emit("canvas-text", {
              method: methodName,
              text: value,
            });
          }
        } catch (_) {}
        return original.call(this, text, ...rest);
      };
    };

    wrap("fillText");
    wrap("strokeText");
    proto.__redIqCanvasWrapped = true;
  };

  const runProbes = () => {
    const candidates = [
      "/api/v1/openets",
      "/api/v1/markets",
      "/api/configuration",
    ];

    window.setTimeout(() => {
      candidates.forEach((url) => {
        fetch(url, { credentials: "include" })
          .then(async (response) => {
            let text = "";
            try {
              text = await response.text();
            } catch (_) {}
            emit("probe", {
              url,
              status: response.status,
              text: text.slice(0, 4000),
            });
          })
          .catch((error) => {
            emit("probe", {
              url,
              error: String(error),
            });
          });
      });
    }, 2500);
  };

  patchWebSocket();
  patchFetch();
  patchXhr();
  patchCanvasText();
  patchCommandBridge();
  runProbes();
})();
