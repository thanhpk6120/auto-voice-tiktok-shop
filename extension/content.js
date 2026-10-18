/**
 * content.js — hook WebSocket cua trang + MutationObserver tren khung chat dashboard.
 *
 * Chien luoc 2 lop (khung selector mem deo):
 *   1. HOOK WebSocket: chan tin nhan ma dashboard nhan duoc, thu parse JSON tim
 *      message/comment/gift/order. Nhanh, chinh xac hon, nhung phu thuoc format
 *      noi bo -> khi doi format thi lop 2 van chay.
 *   2. DOM OBSERVER: theo doi khung chat, doc tung dong moi, phan loai bang nhieu
 *      selector fallback + heuristic text (join / chat / gift / order).
 *
 * Event gui ve background.js qua chrome.runtime.sendMessage, sau do background
 * day tiep ve ws://127.0.0.1:8765 (xem background.js).
 */

(() => {
  const CHANNEL = "tiktok-live-bridge";
  const DEDUPE_WINDOW_MS = 5000;
  const debug = (...args) => console.debug("[bridge/content]", ...args);

  // ---------------------------------------------------------------- selectors
  // Nhieu fallback, khong hard-code 1 class. Thu tu tu cu the -> tong quat.
  const CONTAINER_SELECTORS = [
    '[data-e2e="chat-list"]',
    '[data-e2e="comment-list"]',
    ".webcast-chatroom___items",
    ".webcast-chatroom",
    '[class*="chatroom"][class*="items"]',
    '[class*="comment-list"]',
    '[class*="CommentList"]',
    '[role="log"][aria-live]',
    'div[class*="chat"][class*="list"]',
    'div[class*="ChatList"]',
  ];

  const ROW_SELECTORS = [
    '[data-e2e="comment-item"]',
    '[data-e2e*="comment"]',
    '[data-e2e*="chat-item"]',
    ".comment-item",
    ".chat-item",
    '[class*="comment-item"]',
    '[class*="chat-item"]',
    '[class*="message-item"]',
    '[class*="danmaku"]',
    '[class*="barrage"]',
    '[role="listitem"]',
    'div[class*="chat"] > div',
    'div[class*="comment"] > div',
  ];

  const NICK_SELECTORS = [
    '[data-e2e*="nickname"]',
    '[class*="nickname"]',
    '[class*="Nickname"]',
    '[class*="user-name"]',
    '[class*="UserName"]',
    '[class*="username"]',
    '[data-user]',
    "span[class*='name']",
  ];

  const TEXT_SELECTORS = [
    '[data-e2e*="comment-text"]',
    '[class*="comment-text"]',
    '[class*="commentText"]',
    '[class*="content"]',
    '[class*="text"]',
    "span",
  ];

  const ROW_HINTS = [
    "comment", "chat", "message", "danmaku", "barrage", "gift", "order",
    "listitem", "gift-item", "order-item",
  ];

  // ------------------------------------------------------------------ patterns
  const JOIN_RE = /^(?<user>[^:：]{1,40}?)\s+(?:đã tham gia|vừa tham gia|vào phòng|đã vào|joined|has joined)\b/i;
  const ORDER_RE = /^(?<user>[^:：]{1,40}?)\s+(?:đã đặt đơn|đã chốt đơn|vừa chốt đơn|vừa đặt hàng|đã mua|placed an order|ordered|purchased)\b(?<rest>.*)$/i;
  const GIFT_RE = /^(?<user>[^:：]{1,40}?)\s+(?:đã tặng|vừa tặng|sent|tặng)\s+(?<gift>.+?)(?:\s*[x×*]\s*(?<count>\d+))?\s*$/i;
  const CHAT_RE = /^(?<user>[^:：]{1,40}?)\s*[:：]\s*(?<text>.+)$/;
  const VIEW_RE = /^(?<user>[^:：]{1,40}?)\s+(?:đang xem sản phẩm|đang xem|bấm xem|is viewing product|is viewing)\b(?<product>.*)$/i;
  const AMOUNT_RE = /(\d[\d.,]{2,})/;

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim().replace(/^[-–—|:\s]+|[-–—|:\s]+$/g, "");

  // ------------------------------------------------------------------- parser
  function classifyLine(line) {
    const text = clean(line);
    if (!text) return null;

    let m = text.match(JOIN_RE);
    if (m) return { type: "join", user: clean(m.groups.user) };

    m = text.match(ORDER_RE);
    if (m) {
      const event = { type: "order", user: clean(m.groups.user) };
      let rest = clean(m.groups.rest);
      const amount = rest.match(AMOUNT_RE);
      if (amount) {
        event.amount = parseInt(amount[1].replace(/[.,]/g, ""), 10);
        rest = clean(rest.replace(amount[1], ""));
      }
      rest = clean(rest.replace(/^(for|của|sản phẩm|đơn|order)\s+/i, "").replace(/(đ|vnd|₫)$/i, ""));
      if (rest) event.product = rest;
      return event;
    }
    m = text.match(VIEW_RE);
    if (m) {
      return {
        type: "viewing_product",
        user: clean(m.groups.user),
        product: clean(m.groups.product) || "sản phẩm trên live",
        text: text,
      };
    }


    m = text.match(GIFT_RE);
    if (m) {
      return {
        type: "gift",
        user: clean(m.groups.user),
        gift: clean(m.groups.gift),
        count: m.groups.count ? parseInt(m.groups.count, 10) : 1,
      };
    }

    m = text.match(CHAT_RE);
    if (m) {
      const body = clean(m.groups.text);
      if (body) return { type: "chat", user: clean(m.groups.user), text: body };
    }
    return null;
  }

  function queryFirst(root, selectors) {
    for (const selector of selectors) {
      try {
        const el = root.querySelector(selector);
        if (el && clean(el.textContent)) return el;
      } catch (err) {
        debug("selector loi:", selector, err);
      }
    }
    return null;
  }

  function classTokens(el) {
    return (el.className && typeof el.className === "string" ? el.className : "")
      .toLowerCase().split(/[^a-z0-9-]+/).filter(Boolean);
  }

  function isRowElement(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.getAttribute("role") === "listitem") return true;
    const tokens = classTokens(el);
    if (tokens.some((t) => ROW_HINTS.some((hint) => t.includes(hint)))) return true;
    const e2e = (el.getAttribute("data-e2e") || "").toLowerCase();
    return ROW_HINTS.some((hint) => e2e.includes(hint));
  }

  /** Doc 1 dong DOM -> event (hoac null). Selector mem deo + fallback theo text. */
  function rowToEvent(row) {
    const nicknameEl = queryFirst(row, NICK_SELECTORS);
    let textEl = queryFirst(row, TEXT_SELECTORS);
    if (textEl === nicknameEl) textEl = null;
    const nickname = nicknameEl ? clean(nicknameEl.textContent) : "";
    const body = textEl ? clean(textEl.textContent) : "";
    const line = clean(row.textContent);

    const attrType = ((row.getAttribute("data-event") || row.getAttribute("data-type") ||
      row.getAttribute("data-msg-type") || row.getAttribute("data-e2e")) || "").toLowerCase();

    let type = attrType.includes("gift") ? "gift"
      : attrType.includes("order") ? "order"
        : attrType.includes("join") ? "join"
          : attrType.includes("chat") || attrType.includes("comment") || attrType.includes("message") ? "chat"
            : null;

    const classified = classifyLine(line);
    // Text khop ro join/gift/order thi tin text hon la suy dien tu class
    if (classified && classified.type !== "chat") type = classified.type;
    else if (!type && classified) type = classified.type;

    if (!type) return null;

    const event = { type, source: "content.js" };

    if (type === "chat") {
      let text = body;
      if (!text && classified && classified.type === "chat") {
        event.user = classified.user;
        event.text = classified.text;
        return event;
      }
      const user = nickname || (classified ? classified.user : "") || clean(text.split(/[:：]/)[0]);
      if (!user || !text) return null;
      event.user = user;
      event.text = clean(text.replace(new RegExp("^" + escapeRe(user) + "\\s*[:：]?\\s*"), "")) || text;
      return event;
    }

    if (type === "gift") {
      const giftName = row.getAttribute("data-gift-name") || row.getAttribute("data-gift") ||
        (classified && classified.type === "gift" ? classified.gift : "");
      const count = parseInt(row.getAttribute("data-count") || row.getAttribute("data-gift-count") || "", 10) ||
        (classified && classified.type === "gift" ? classified.count : 1);
      event.user = nickname || (classified ? classified.user : "");
      if (!event.user) return null;
      event.gift = clean(giftName) || "quà";
      event.count = count > 0 ? count : 1;
      return event;
    }

    if (type === "order") {
      event.user = nickname || (classified ? classified.user : "");
      if (!event.user) return null;
      const product = row.getAttribute("data-product") || row.getAttribute("data-product-name") ||
        (classified ? classified.product : "");
      const amount = parseInt(row.getAttribute("data-amount") || row.getAttribute("data-price") || "", 10) ||
        (classified ? classified.amount : 0);
      if (product) event.product = clean(product);
      if (amount > 0) event.amount = amount;
      return event;
    }

    // join
    event.user = nickname || (classified ? classified.user : "");
    return event.user ? event : null;
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // ------------------------------------------------------------------- dedupe
  const recent = new Map(); // fingerprint -> ts

  function fingerprint(event) {
    return [event.type, event.user, event.text || event.gift || event.product || ""].join("|");
  }

  function fresh(event) {
    const key = fingerprint(event);
    const now = Date.now();
    const last = recent.get(key);
    if (last && now - last < DEDUPE_WINDOW_MS) return false;
    recent.set(key, now);
    for (const [k, ts] of recent) if (now - ts > DEDUPE_WINDOW_MS * 4) recent.delete(k);
    return true;
  }

  // -------------------------------------------------------------------- send
  let buffer = [];
  let flushTimer = null;

  function emit(event) {
    if (!event || !event.type || !event.user) return;
    if (!fresh(event)) return;
    event.ts = Date.now() / 1000;
    buffer.push(event);
    if (buffer.length >= 10) flush();
    else if (!flushTimer) flushTimer = setTimeout(flush, 300);
  }

  function flush() {
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null; }
    if (!buffer.length) return;
    const events = buffer;
    buffer = [];
    try {
      chrome.runtime.sendMessage({ channel: CHANNEL, action: "events", events }, (reply) => {
        if (chrome.runtime.lastError) return;
        debug("da gui", events.length, "event", reply);
      });
    } catch (err) {
      debug("sendMessage loi:", err);
    }
  }

  // ---------------------------------------------------------------- observers
  const seenRows = new WeakSet();

  function scanRow(row) {
    if (!row || seenRows.has(row)) return;
    seenRows.add(row);
    const event = rowToEvent(row);
    if (event) emit(event);
  }

  function findContainers() {
    const found = [];
    for (const selector of CONTAINER_SELECTORS) {
      try {
        document.querySelectorAll(selector).forEach((el) => found.push(el));
      } catch (err) { /* selector khong hop le voi trang nay */ }
    }
    if (found.length) return found;
    // Fallback cuoi: cha cua dong chat dau tien tim duoc
    for (const selector of ROW_SELECTORS) {
      try {
        const row = document.querySelector(selector);
        if (row && row.parentElement) return [row.parentElement];
      } catch (err) { /* bo qua */ }
    }
    return [];
  }

  /** Quet lai ca khung: dung khi chua tim duoc container hoac container bi remount. */
  function fullScan() {
    let total = 0;
    for (const selector of ROW_SELECTORS) {
      try {
        document.querySelectorAll(selector).forEach((row) => {
          if (!isRowElement(row)) return;
          seenRows.add(row);
          const event = rowToEvent(row);
          if (event && fresh(event)) { event.ts = Date.now() / 1000; buffer.push(event); total += 1; }
        });
      } catch (err) { /* bo qua selector loi */ }
    }
    // fullScan chi dung de gui event *moi*; lan dau tien sau khi load trang
    if (total && !started) debug("fullScan (lan dau):", total, "event");
    if (buffer.length) flush();
  }

  let started = false;

  function attach() {
    const containers = findContainers();
    if (!containers.length) return false;

    for (const container of containers) {
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType !== 1) return;
            if (isRowElement(node)) scanRow(node);
            node.querySelectorAll && node.querySelectorAll(ROW_SELECTORS.join(",")).forEach((row) => {
              if (isRowElement(row)) scanRow(row);
            });
          });
          if (mutation.type === "characterData" || mutation.type === "childList") {
            const target = mutation.target.nodeType === 1 ? mutation.target : mutation.target.parentElement;
            const row = target && (isRowElement(target) ? target : target.closest(ROW_SELECTORS.join(",")));
            if (row && isRowElement(row)) scanRow(row);
          }
        }
      });
      observer.observe(container, { childList: true, subtree: true, characterData: true });
      debug("gan observer vao", container);
    }

    started = true;
    fullScan(); // bat cac dong da co san khi vua load trang
    return true;
  }

  let attachTimer = null;
  function ensureAttached() {
    if (attach()) return;
    if (attachTimer) return;
    attachTimer = setTimeout(() => {
      attachTimer = null;
      ensureAttached();
    }, 2000); // SPA doi view -> gan lai
  }

  // ------------------------------------------------------- HOOK WebSocket API
  // Dashboard push comment/gift/order qua WebSocket -> doc truc tiep tin nhan.
  const NativeWebSocket = window.WebSocket;

  function hookWebSocket() {
    function WrappedWebSocket(url, protocols) {
      const ws = protocols === undefined ? new NativeWebSocket(url) : new NativeWebSocket(url, protocols);
      try {
        const isLiveHost = typeof url === "string" && /tiktok|live|webcast/i.test(url);
        if (isLiveHost) {
          ws.addEventListener("message", (event) => {
            try { handleSocketMessage(event.data); } catch (err) { debug("hook parse loi", err); }
          });
          debug("hook WebSocket:", String(url).slice(0, 120));
        }
      } catch (err) { debug("hook loi:", err); }
      return ws;
    }

    WrappedWebSocket.prototype = NativeWebSocket.prototype;
    Object.assign(WrappedWebSocket, {
      CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3,
    });
    window.WebSocket = WrappedWebSocket;
  }

  /** Thu boc JSON tin nhan WebSocket -> event (schema noi bo co the doi). */
  function handleSocketMessage(data) {
    if (typeof data !== "string" || data.length > 200000) return;
    let payload;
    try { payload = JSON.parse(data); } catch (err) { return; }
    const found = [];
    walk(payload, found, 0);
    found.forEach(emit);
  }

  const TYPE_HINTS = {
    chat: ["comment", "chat", "danmaku", "message"],
    gift: ["gift"],
    order: ["order", "purchase", "paid"],
    join: ["join", "member", "enter"],
  };

  function classifySocketNode(node) {
    const rawType = String(node.method || node.type || node.msg_type || node.msgType ||
      node.event_type || node.eventType || node.message_type || "").toLowerCase();
    if (!rawType) return null;
    for (const [type, hints] of Object.entries(TYPE_HINTS)) {
      if (hints.some((hint) => rawType.includes(hint))) return type;
    }
    return null;
  }

  function walk(node, out, depth) {
    if (!node || depth > 6 || out.length > 200) return;
    if (Array.isArray(node)) {
      node.forEach((item) => walk(item, out, depth + 1));
      return;
    }
    if (typeof node !== "object") return;

    const type = classifySocketNode(node);
    if (type) {
      const user = pickUser(node);
      if (user) {
        const event = { type, user, source: "content.js/ws" };
        if (type === "chat") {
          const text = pickText(node);
          if (text) event.text = text;
          else return; // chat ma khong co text -> bo
        } else if (type === "gift") {
          event.gift = pickGift(node);
          event.count = pickCount(node);
        } else if (type === "order") {
          const product = pickProduct(node);
          if (product) event.product = product;
          const amount = pickAmount(node);
          if (amount) event.amount = amount;
        }
        out.push(event);
      }
    }
    Object.values(node).forEach((value) => {
      if (value && typeof value === "object") walk(value, out, depth + 1);
    });
  }

  const pickUser = (n) => clean(
    n.user?.nickname || n.user?.nick_name || n.user?.name || n.user?.unique_id ||
    n.nickname || n.user_name || n.userName || n.username || n.display_name || "");
  const pickText = (n) => clean(n.comment || n.content || n.text || n.message || n.body || "");
  const pickGift = (n) => clean(n.gift?.name || n.gift_name || n.giftName || n.gift?.describe || "") || "quà";
  const pickCount = (n) => parseInt(n.gift?.repeat_count ?? n.repeat_count ?? n.count ?? n.gift_count ?? 1, 10) || 1;
  const pickProduct = (n) => clean(
    n.product?.title || n.product_name || n.productName || n.item?.title || n.order?.product_name || "");
  const pickAmount = (n) => parseInt(
    n.order?.amount ?? n.amount ?? n.total ?? n.price ?? n.pay_amount ?? 0, 10) || 0;

  // --------------------------------------------------------------------- boot
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureAttached, { once: true });
  } else {
    ensureAttached();
  }
  hookWebSocket();

  // SPA doi trang -> container bi remount, quet lai dinh ky
  setInterval(ensureAttached, 10000);

  window.addEventListener("beforeunload", flush);
  debug("content script san sang (url:", location.href, ")");
})();
