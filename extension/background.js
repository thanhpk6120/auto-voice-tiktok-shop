/**
 * background.js (MV3 service worker)
 * Nhan event da chuan hoa tu content.js -> gui ve WebSocket local (event bridge).
 *
 * - Tu dong reconnect khi mat ket noi (backoff).
 * - Dem event theo type, luu vao chrome.storage.local (xem o console bang
 *   `chrome.storage.local.get(console.log)`).
 */

const BRIDGE_URL = "ws://127.0.0.1:8765";
const RECONNECT_MS = 3000;
const MAX_QUEUE = 200; // ponytail: giu toi da 200 event khi mat ket noi

let socket = null;
let reconnectTimer = null;
let queue = [];
let counts = { join: 0, chat: 0, gift: 0, order: 0, invalid: 0 };

function persist() {
  const stats = { counts, connected: !!socket && socket.readyState === WebSocket.OPEN, updatedAt: Date.now() };
  chrome.storage.local.set({ bridgeStats: stats }).catch(() => {});
  chrome.action.setBadgeText({ text: String(counts.chat + counts.gift + counts.order + counts.join || "") });
  chrome.action.setBadgeBackgroundColor({ color: "#1f6feb" });
}

function connect() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
  try {
    socket = new WebSocket(BRIDGE_URL);
  } catch (err) {
    scheduleReconnect();
    return;
  }

  socket.addEventListener("open", () => {
    console.log("[bridge] da ket noi", BRIDGE_URL);
    persist();
    const pending = queue;
    queue = [];
    pending.forEach(send);
  });

  socket.addEventListener("message", (event) => {
    // Server tra ack / error / pong -> log de debug
    console.debug("[bridge] server:", event.data);
  });

  socket.addEventListener("close", () => {
    console.warn("[bridge] mat ket noi, thu lai sau", RECONNECT_MS, "ms");
    socket = null;
    persist();
    scheduleReconnect();
  });

  socket.addEventListener("error", () => {
    // loi thuong di kem close -> de close xu ly reconnect
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_MS);
}

function send(event) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    if (queue.length < MAX_QUEUE) queue.push(event);
    connect();
    return;
  }
  try {
    socket.send(JSON.stringify(event));
    counts[event.type] = (counts[event.type] || 0) + 1;
    persist();
  } catch (err) {
    console.warn("[bridge] gui loi:", err);
    if (queue.length < MAX_QUEUE) queue.push(event);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.channel !== "tiktok-live-bridge") return false;

  if (message.action === "events" && Array.isArray(message.events)) {
    message.events.forEach(send);
    sendResponse({ ok: true, sent: message.events.length });
    return true;
  }

  if (message.action === "invalid") {
    counts.invalid += 1;
    persist();
    sendResponse({ ok: true });
    return true;
  }

  if (message.action === "stats") {
    sendResponse({ counts, connected: !!socket && socket.readyState === WebSocket.OPEN, queued: queue.length });
    return true;
  }

  return false;
});

// Heartbeat: giu service worker thuc + bao trang thai dinh ky
setInterval(() => {
  chrome.storage.local.get("bridgeStats", (data) => {
    if (data && data.bridgeStats) {
      console.debug("[bridge] heartbeat", data.bridgeStats);
    }
  });
}, 15000);

connect();
