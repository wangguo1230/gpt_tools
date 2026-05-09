import "./styles.css";
import {
  checkHealth,
  generateLink,
  getOrderDetail,
  listOrders,
  querySubscriptionStatus,
  resolveBillingCurrency,
} from "./api";
import { currencyForCountry } from "./countryCurrency";

const state = {
  activeService: "subscription",
  latestSubscription: null,
  latestTokenInput: "",
  orderQuery: {
    keyword: "",
    status: "",
    plan_type: "",
    limit: 20,
    offset: 0,
  },
};

function qs(selector) {
  return document.querySelector(selector);
}

function qsAll(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setNotice(message, tone = "neutral") {
  const el = qs("#notice");
  if (!el) return;
  el.textContent = message;
  el.dataset.tone = tone;
}

function setButtonLoading(button, loading, textWhileLoading) {
  if (!button) return;
  if (loading) {
    button.dataset.prevText = button.textContent;
    button.disabled = true;
    button.textContent = textWhileLoading;
    return;
  }
  button.disabled = false;
  if (button.dataset.prevText) {
    button.textContent = button.dataset.prevText;
  }
}

function switchService(next) {
  state.activeService = next;
  qsAll("[data-service-btn]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.serviceBtn === next);
  });
  qsAll("[data-service-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.servicePanel !== next;
  });
}

function getAuthContext() {
  return {
    token: String(qs("#token-input")?.value || "").trim(),
    proxy: String(qs("#proxy-input")?.value || "").trim(),
  };
}

const CHANNEL_LABEL_MAP = {
  google_play_like: "安卓订阅",
  apple_iap_like: "iOS订阅",
  web_stripe_like: "卡充",
  not_purchased: "未订阅",
  active_unknown: "渠道未知",
  paid_unknown: "渠道未知",
  unknown: "未知",
};

function getChannelLabel(payload) {
  const guess = String(payload.channel_guess || "").trim().toLowerCase();
  return CHANNEL_LABEL_MAP[guess] || CHANNEL_LABEL_MAP.unknown;
}

function getChannelChipClass(payload) {
  const guess = String(payload.channel_guess || "").trim().toLowerCase();
  if (guess === "google_play_like") return "android";
  if (guess === "apple_iap_like") return "ios";
  if (guess === "web_stripe_like") return "card";
  return "unknown";
}

function formatTimeUtc8(rawValue) {
  const text = String(rawValue || "").trim();
  if (!text) return "-";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const map = Object.fromEntries(parts.filter((item) => item.type !== "literal").map((item) => [item.type, item.value]));
  return `${map.year}/${map.month}/${map.day} ${map.hour}:${map.minute}:${map.second}`;
}

function getRemainingSubscriptionInfo(rawEndTime) {
  const text = String(rawEndTime || "").trim();
  if (!text) return { text: "无法计算剩余时间", tone: "neutral", days: null };
  const endAt = new Date(text);
  if (Number.isNaN(endAt.getTime())) return { text: "无法计算剩余时间", tone: "neutral", days: null };
  const now = new Date();
  const diffMs = endAt.getTime() - now.getTime();
  if (diffMs <= 0) return { text: "订阅已到期", tone: "expired", days: 0 };
  const days = Math.ceil(diffMs / (24 * 60 * 60 * 1000));
  if (days <= 3) return { text: `订阅有效期剩余 ${days} 天`, tone: "danger", days };
  if (days <= 7) return { text: `订阅有效期剩余 ${days} 天`, tone: "warn", days };
  return { text: `订阅有效期剩余 ${days} 天`, tone: "safe", days };
}

function findEmailInObject(payload, depth = 0) {
  if (depth > 8 || payload == null) return "";
  if (typeof payload === "string") {
    const value = payload.trim();
    if (value.includes("@")) return value;
    return "";
  }
  if (Array.isArray(payload)) {
    for (const item of payload) {
      const found = findEmailInObject(item, depth + 1);
      if (found) return found;
    }
    return "";
  }
  if (typeof payload !== "object") return "";

  for (const [key, value] of Object.entries(payload)) {
    if (String(key).toLowerCase() === "email") {
      const candidate = String(value || "").trim();
      if (candidate.includes("@")) return candidate;
    }
  }
  for (const value of Object.values(payload)) {
    const found = findEmailInObject(value, depth + 1);
    if (found) return found;
  }
  return "";
}

function decodeBase64UrlJson(segment) {
  try {
    const normalized = String(segment || "").replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = atob(padded);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

function extractEmailFromJwt(jwtText) {
  const token = String(jwtText || "").trim();
  if (!token || !token.includes(".")) return "";
  const parts = token.split(".");
  if (parts.length < 2) return "";
  const payload = decodeBase64UrlJson(parts[1]);
  if (!payload || typeof payload !== "object") return "";
  const direct = findEmailInObject(payload);
  return direct || "";
}

function extractEmailFromTokenInput(rawTokenInput) {
  const raw = String(rawTokenInput || "").trim();
  if (!raw) return "";
  let candidate = raw;
  const lower = candidate.toLowerCase();
  if (lower.startsWith("authorization:")) {
    candidate = candidate.split(":", 2).pop()?.trim() || "";
  }
  if (candidate.toLowerCase().startsWith("bearer ")) {
    candidate = candidate.slice(7).trim();
  }

  if (raw.startsWith("{") || raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw);
      const jsonEmail = findEmailInObject(parsed);
      if (jsonEmail) return jsonEmail;
      const tokenKeys = ["accessToken", "access_token", "token"];
      const queue = [parsed];
      let depth = 0;
      while (queue.length && depth <= 8) {
        const current = queue.shift();
        depth += 1;
        if (current && typeof current === "object") {
          if (Array.isArray(current)) {
            queue.push(...current);
          } else {
            for (const [key, value] of Object.entries(current)) {
              if (tokenKeys.includes(key) && typeof value === "string") {
                const tokenEmail = extractEmailFromJwt(value);
                if (tokenEmail) return tokenEmail;
              } else if (value && typeof value === "object") {
                queue.push(value);
              }
            }
          }
        }
      }
    } catch {
      // fallback to raw token parse
    }
  }

  return extractEmailFromJwt(candidate);
}

function renderSubscriptionResult(payload) {
  const box = qs("#subscription-result");
  if (!box) return;
  if (!payload) {
    box.innerHTML = '<p class="placeholder">等待查询订阅状态...</p>';
    state.latestSubscription = null;
    updateSubscriptionActions();
    return;
  }
  state.latestSubscription = payload;
  const paid = Boolean(payload.is_paid);
  const hasError = !Boolean(payload.ok) || !Boolean(payload.account_id);
  const alertTitle = hasError ? "查询失败，请检查 token 是否有效" : "查询成功，已获取订阅信息";
  const alertDesc = hasError
    ? payload.error || "无法加载账号订阅信息，请稍后重试。"
    : "可继续生成支付方式，或切换到订单查询查看记录。";
  const autoRenew = payload.has_active_subscription ? "已开启" : "未开启";
  const accountState = hasError ? "异常" : payload.is_delinquent ? "欠费风险" : "正常";
  const channelSummary = getChannelLabel(payload);
  const channelChipClass = getChannelChipClass(payload);
  const subscriptionState = hasError ? "未知" : payload.has_active_subscription ? "有效" : "未开通";
  const cycle = payload.billing_period || "-";
  const endRaw = payload.renews_at || payload.expires_at;
  const endsAt = formatTimeUtc8(endRaw);
  const startedAt = formatTimeUtc8(payload.subscription_start_at);
  const remainInfo = hasError
    ? { text: "无法计算剩余时间", tone: "neutral", days: null }
    : payload.has_active_subscription
      ? getRemainingSubscriptionInfo(endRaw)
      : { text: "当前无有效订阅", tone: "inactive", days: null };
  const endTileToneClass =
    remainInfo.tone === "danger" || remainInfo.tone === "expired"
      ? "tile-end-danger"
      : remainInfo.tone === "warn"
        ? "tile-end-warn"
        : remainInfo.tone === "safe"
          ? "tile-end-safe"
          : "tile-end-neutral";
  const remainBarToneClass = `remain-${remainInfo.tone}`;
  const emailFromToken = extractEmailFromTokenInput(state.latestTokenInput);
  const accountEmail = String(payload.email || emailFromToken || "-").trim() || "-";
  const planType = String(payload.plan_type || "-").trim();
  const tiles = [
    {
      key: "当前套餐",
      value: `<span class="plan-chip">${escapeHtml(planType.toLowerCase() || "-")}</span>`,
      isHtml: true,
      toneClass: "tile-plan",
    },
    {
      key: "订阅状态",
      value: subscriptionState,
      toneClass: payload.has_active_subscription ? "tile-active" : "tile-neutral",
    },
    {
      key: "订阅渠道",
      value: `<span class="channel-chip ${channelChipClass}">${escapeHtml(channelSummary)}</span>`,
      isHtml: true,
      toneClass: "tile-channel",
      valueClass: "emphasis",
    },
    {
      key: "订阅结束时间",
      value: endsAt,
      toneClass: `tile-end ${endTileToneClass}`,
      valueClass: "emphasis end-time",
    },
    { key: "订阅时间", value: startedAt, toneClass: "tile-neutral" },
    { key: "自动续费", value: autoRenew, toneClass: payload.has_active_subscription ? "tile-active" : "tile-neutral" },
    { key: "计费周期", value: cycle, toneClass: "tile-neutral" },
    { key: "货币单位", value: payload.billing_currency || "-", toneClass: "tile-neutral" },
    { key: "账号状态", value: accountState, toneClass: accountState === "正常" ? "tile-active" : "tile-risk" },
  ];
  box.innerHTML = `
    <div class="subscription-hero">
      <div>
        <p class="meta">订阅总览</p>
        <h3>${escapeHtml(paid ? "订阅中" : "未订阅")}</h3>
        <p class="hero-email">账号邮箱：${escapeHtml(accountEmail)}</p>
      </div>
      <span class="badge ${paid ? "ok" : "warn"}">${escapeHtml((planType || "unknown").toUpperCase())}</span>
    </div>
    <div class="alert-row ${hasError ? "error" : "success"}">
      <div class="alert-title">${escapeHtml(alertTitle)}</div>
      <div class="alert-desc">${escapeHtml(alertDesc)}</div>
    </div>
    <div class="account-grid">
      ${tiles
        .map(
          (tile) => `
        <div class="account-tile ${escapeHtml(tile.toneClass || "")}">
          <div class="tile-key">${escapeHtml(tile.key)}</div>
          <div class="tile-val ${escapeHtml(tile.valueClass || "")}">${tile.isHtml ? tile.value : escapeHtml(tile.value || "-")}</div>
          ${tile.hint ? `<div class="tile-hint">${escapeHtml(tile.hint)}</div>` : ""}
        </div>
      `,
        )
        .join("")}
    </div>
    <div class="remain-bar ${escapeHtml(remainBarToneClass)}">${escapeHtml(remainInfo.text)}</div>
    ${payload.error && !hasError ? `<p class="warn-text">提示：${escapeHtml(payload.error)}</p>` : ""}
  `;
  updateSubscriptionActions();
}

function updateSubscriptionActions() {
  const portalButton = qs("#open-portal-btn");
  if (!portalButton) return;
  const url = String(state.latestSubscription?.customer_portal_url || "").trim();
  if (url) {
    portalButton.disabled = false;
    portalButton.dataset.url = url;
    portalButton.textContent = "获取历史账单链接";
    return;
  }
  portalButton.disabled = true;
  portalButton.dataset.url = "";
  portalButton.textContent = "历史账单链接不可用";
}

function renderLinkResult(payload) {
  const box = qs("#link-result");
  if (!box) return;
  if (!payload) {
    box.innerHTML = '<p class="placeholder">等待生成支付方式...</p>';
    return;
  }
  const methods = payload.payment_methods || {};
  const rows = [
    ["订单号", payload.order_no || payload.order_id],
    ["套餐", payload.selected_plan],
    ["short", methods.short],
    ["hosted", methods.hosted],
    ["stripe", methods.stripe],
    ["地区", payload.billing_country],
    ["货币", payload.billing_currency],
    ["session_id", payload.checkout_session_id],
  ];
  if (payload.error) rows.push(["提示", payload.error]);
  box.innerHTML = `
    <div class="result-grid">
      ${rows
        .map(
          ([k, v]) => `
        <div class="result-row">
          <div class="result-key">${escapeHtml(k)}</div>
          <div class="result-value">${escapeHtml(v || "-")}</div>
        </div>
      `,
        )
        .join("")}
    </div>
  `;
}

function renderOrderRows(payload) {
  const tbody = qs("#orders-tbody");
  const summary = qs("#orders-summary");
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (summary) summary.textContent = `共 ${payload?.total ?? 0} 条，当前 ${items.length} 条`;

  if (!tbody) return;
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="placeholder">暂无数据</td></tr>';
    return;
  }

  tbody.innerHTML = items
    .map(
      (item) => `
      <tr data-order-id="${item.id}">
        <td>#${item.id}</td>
        <td>${escapeHtml(item.task_no)}</td>
        <td><span class="pill">${escapeHtml(item.plan_type)}</span></td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.account_email || "-")}</td>
        <td>${escapeHtml(item.created_at || "-")}</td>
      </tr>
    `,
    )
    .join("");
}

function renderOrderDetail(payload) {
  const box = qs("#order-detail");
  if (!box) return;
  if (!payload?.item) {
    box.innerHTML = '<p class="placeholder">点击列表行查看订单详情</p>';
    return;
  }
  const item = payload.item;
  const logs = Array.isArray(payload.logs) ? payload.logs : [];
  box.innerHTML = `
    <div class="order-meta">
      <div><b>订单</b> #${item.id} / ${escapeHtml(item.task_no)}</div>
      <div><b>套餐</b> ${escapeHtml(item.plan_type)} | <b>状态</b> ${escapeHtml(item.status)}</div>
      <div><b>短链</b> <span class="mono">${escapeHtml(item.short_url || "-")}</span></div>
      <div><b>支付链</b> <span class="mono">${escapeHtml(item.checkout_url || "-")}</span></div>
      <div><b>错误</b> ${escapeHtml(item.last_error_code || "-")} ${escapeHtml(item.last_error_message || "")}</div>
    </div>
    <div class="log-list">
      ${
        logs.length
          ? logs
              .map(
                (log) => `
            <div class="log-item">
              <div class="log-head">
                <span class="level">${escapeHtml(log.level)}</span>
                <span>${escapeHtml(log.step)}</span>
                <span>${escapeHtml(log.created_at)}</span>
              </div>
              <div class="log-msg">${escapeHtml(log.message)}</div>
            </div>
          `,
              )
              .join("")
          : '<p class="placeholder">暂无日志</p>'
      }
    </div>
  `;
}

async function autoResolveCurrency(form, { silent = false } = {}) {
  const auth = getAuthContext();
  const countryInput = form.querySelector("[name='billing_country']");
  const currencyInput = form.querySelector("[name='billing_currency']");
  const country = String(countryInput?.value || "").trim().toUpperCase();
  const currency = String(currencyInput?.value || "").trim().toUpperCase();
  if (!country) return null;

  const localCurrency = String(currencyForCountry(country) || "").trim().toUpperCase();
  if (localCurrency) {
    if (countryInput) countryInput.value = country;
    if (currencyInput) currencyInput.value = localCurrency;
    if (!silent && localCurrency !== currency) {
      setNotice(`已自动匹配货币：${country} -> ${localCurrency}`, "success");
    }
    return {
      ok: true,
      billing_country: country,
      billing_currency: localCurrency,
      source: "worker_country_map",
    };
  }

  if (!auth.token) {
    if (!silent) setNotice("本地映射未命中，需先输入 token 才能在线解析货币", "danger");
    return null;
  }

  const payload = await resolveBillingCurrency({
    token: auth.token,
    proxy: auth.proxy,
    billing_country: country,
    billing_currency: currency,
  });
  if (countryInput) countryInput.value = String(payload.billing_country || "").toUpperCase();
  if (currencyInput) currencyInput.value = String(payload.billing_currency || "").toUpperCase();
  if (!silent) setNotice(`已自动匹配货币：${payload.billing_country} -> ${payload.billing_currency}`, "success");
  return payload;
}

async function loadOrders() {
  const btn = qs("#search-orders-btn");
  setButtonLoading(btn, true, "查询中...");
  try {
    const payload = await listOrders(state.orderQuery);
    renderOrderRows(payload);
    setNotice("订单查询成功", "success");
  } catch (error) {
    renderOrderRows({ items: [], total: 0 });
    setNotice(error.message || "订单查询失败", "danger");
  } finally {
    setButtonLoading(btn, false);
  }
}

async function loadOrderDetail(orderId) {
  const detailBox = qs("#order-detail");
  if (detailBox) detailBox.innerHTML = '<p class="placeholder">正在加载详情...</p>';
  try {
    const payload = await getOrderDetail(orderId, 40);
    renderOrderDetail(payload);
  } catch (error) {
    renderOrderDetail(null);
    setNotice(error.message || "加载订单详情失败", "danger");
  }
}

function mount() {
  const app = qs("#app");
  app.innerHTML = `
    <header class="topbar">
      <div class="brand-wrap">
        <div class="brand-logo">🐾</div>
        <div>
          <div class="brand-title">ChatGPT 支付助手</div>
          <div class="brand-sub">Token管理 · 订阅状态 · 支付方式 · 订单记录</div>
        </div>
      </div>
      <div class="notice" id="notice" data-tone="neutral">正在初始化...</div>
    </header>

    <main class="layout">
      <section class="workspace-card">
        <div class="workspace-head">
          <h2>数据中心</h2>
          <p>单页三功能：先查订阅，再生成支付方式，最后查订单。</p>
        </div>

        <nav class="service-tabs">
          <button data-service-btn="subscription" class="active">GPT Token 查询</button>
          <button data-service-btn="payment">平台自助服务</button>
          <button data-service-btn="orders">订单查询服务</button>
        </nav>

        <section class="hint-card">
          <h3>如何获取 Token 数据？</h3>
          <ul>
            <li><b>方式1：</b>访问 <code>https://chatgpt.com/api/auth/session</code>，复制页面 JSON。</li>
            <li><b>方式2：</b>直接粘贴 <code>Bearer ...</code> 或 access token。</li>
            <li><b>方式3：</b>也支持包含 <code>access_token / accessToken / token</code> 字段的 JSON。</li>
          </ul>
        </section>

        <section class="auth-card">
          <label class="auth-label">请输入 Token JSON 数据、Refresh Token 或 Access Token</label>
          <textarea id="token-input" rows="6" placeholder="粘贴完整 Token JSON / Bearer token / JWT"></textarea>
          <div class="auth-controls">
            <input id="proxy-input" type="text" value="http://127.0.0.1:10808" placeholder="Proxy (可选): http://127.0.0.1:10808" />
            <button id="query-subscription-btn" type="button">校验Token并查询订阅</button>
            <button id="clear-token-btn" type="button" class="ghost">清空内容</button>
          </div>
        </section>

        <section data-service-panel="subscription" class="service-panel">
          <article class="result-box" id="subscription-result">
            <p class="placeholder">等待查询订阅状态...</p>
          </article>
          <div class="account-actions">
            <button type="button" class="soft blue" id="open-payment-tab-btn">获取订阅支付链接</button>
            <button type="button" class="soft green" id="open-orders-tab-btn">查看订单查询服务</button>
            <button type="button" class="soft purple" id="open-portal-btn" disabled>历史账单链接不可用</button>
          </div>
        </section>

        <section data-service-panel="payment" class="service-panel" hidden>
          <form id="link-form" class="form-grid">
            <label>
              套餐
              <select name="plan">
                <option value="pro">Pro</option>
                <option value="plus">Plus</option>
              </select>
            </label>
            <label>
              默认返回链接
              <select name="link_mode">
                <option value="short">short</option>
                <option value="hosted">hosted</option>
                <option value="long">long</option>
              </select>
            </label>
            <label>
              地区 (Country)
              <input type="text" name="billing_country" maxlength="8" placeholder="例如 US" />
            </label>
            <label>
              货币 (Currency)
              <input type="text" name="billing_currency" maxlength="8" placeholder="自动识别，例如 USD" />
            </label>
            <div class="form-actions">
              <button id="generate-link-btn" type="submit">生成支付方式</button>
            </div>
          </form>
          <article class="result-box" id="link-result">
            <p class="placeholder">等待生成支付方式...</p>
          </article>
        </section>

        <section data-service-panel="orders" class="service-panel" hidden>
          <form id="order-query-form" class="query-grid">
            <input name="keyword" placeholder="关键词：task_no / 邮箱 / 链接" />
            <select name="status">
              <option value="">全部状态</option>
              <option value="processing">processing</option>
              <option value="generated">generated</option>
              <option value="failed">failed</option>
            </select>
            <select name="plan_type">
              <option value="">全部套餐</option>
              <option value="pro">pro</option>
              <option value="plus">plus</option>
              <option value="pro5x">pro5x(兼容历史)</option>
              <option value="pro20x">pro20x(兼容历史)</option>
            </select>
            <input name="limit" type="number" min="1" max="100" value="20" />
            <button id="search-orders-btn" type="submit">查询订单</button>
          </form>

          <div id="orders-summary" class="summary">共 0 条，当前 0 条</div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Task No</th>
                  <th>套餐</th>
                  <th>状态</th>
                  <th>账号邮箱</th>
                  <th>创建时间</th>
                </tr>
              </thead>
              <tbody id="orders-tbody">
                <tr><td colspan="6" class="placeholder">暂无数据</td></tr>
              </tbody>
            </table>
          </div>

          <article class="result-box" id="order-detail">
            <p class="placeholder">点击列表行查看订单详情</p>
          </article>
        </section>
      </section>
    </main>
  `;

  qsAll("[data-service-btn]").forEach((button) => {
    button.addEventListener("click", () => switchService(button.dataset.serviceBtn));
  });

  qs("#clear-token-btn").addEventListener("click", () => {
    qs("#token-input").value = "";
    state.latestTokenInput = "";
    renderSubscriptionResult(null);
    setNotice("已清空 Token 输入", "neutral");
  });

  qs("#query-subscription-btn").addEventListener("click", async () => {
    const { token, proxy } = getAuthContext();
    if (!token) {
      setNotice("请先输入 token", "danger");
      return;
    }
    state.latestTokenInput = token;
    const button = qs("#query-subscription-btn");
    setButtonLoading(button, true, "查询中...");
    renderSubscriptionResult(null);
    try {
      const payload = await querySubscriptionStatus({ token, proxy });
      renderSubscriptionResult(payload);
      switchService("subscription");
      setNotice("订阅状态查询成功", "success");
    } catch (error) {
      renderSubscriptionResult({ error: error.message || "订阅状态查询失败" });
      setNotice(error.message || "订阅状态查询失败", "danger");
    } finally {
      setButtonLoading(button, false);
    }
  });

  qs("#open-payment-tab-btn").addEventListener("click", () => {
    switchService("payment");
    setNotice("已切换到支付方式生成", "neutral");
  });
  qs("#open-orders-tab-btn").addEventListener("click", () => {
    switchService("orders");
    setNotice("已切换到订单查询", "neutral");
  });
  qs("#open-portal-btn").addEventListener("click", () => {
    const url = String(qs("#open-portal-btn").dataset.url || "").trim();
    if (!url) {
      setNotice("当前账号未返回账单门户链接", "danger");
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  });

  const linkForm = qs("#link-form");
  const countryInput = linkForm.querySelector("[name='billing_country']");
  countryInput.addEventListener("change", async () => {
    try {
      await autoResolveCurrency(linkForm, { silent: false });
    } catch (error) {
      setNotice(error.message || "自动识别货币失败", "danger");
    }
  });

  linkForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const auth = getAuthContext();
    if (!auth.token) {
      setNotice("请先在上方填写 token 并校验订阅状态", "danger");
      return;
    }

    const submitButton = qs("#generate-link-btn");
    const form = new FormData(event.currentTarget);
    const payload = {
      token: auth.token,
      proxy: auth.proxy,
      plan: String(form.get("plan") || "pro").trim().toLowerCase(),
      link_mode: String(form.get("link_mode") || "short").trim(),
      billing_country: String(form.get("billing_country") || "").trim().toUpperCase(),
      billing_currency: String(form.get("billing_currency") || "").trim().toUpperCase(),
    };
    if (payload.billing_country && !payload.billing_currency) {
      try {
        const resolved = await autoResolveCurrency(linkForm, { silent: true });
        if (resolved?.billing_currency) {
          payload.billing_currency = String(resolved.billing_currency || "").trim().toUpperCase();
          linkForm.querySelector("[name='billing_currency']").value = payload.billing_currency;
        }
      } catch {
        // keep user input
      }
    }

    setButtonLoading(submitButton, true, "生成中...");
    renderLinkResult(null);
    try {
      const result = await generateLink(payload);
      renderLinkResult(result);
      setNotice("支付方式生成成功", "success");
    } catch (error) {
      renderLinkResult({ error: error.message || "支付方式生成失败" });
      setNotice(error.message || "支付方式生成失败", "danger");
    } finally {
      setButtonLoading(submitButton, false);
    }
  });

  qs("#order-query-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    state.orderQuery.keyword = String(form.get("keyword") || "").trim();
    state.orderQuery.status = String(form.get("status") || "").trim();
    state.orderQuery.plan_type = String(form.get("plan_type") || "").trim();
    state.orderQuery.limit = Number(form.get("limit") || 20);
    state.orderQuery.offset = 0;
    await loadOrders();
  });

  qs("#orders-tbody").addEventListener("click", async (event) => {
    const row = event.target.closest("tr[data-order-id]");
    if (!row) return;
    qsAll("#orders-tbody tr").forEach((tr) => tr.classList.remove("active-row"));
    row.classList.add("active-row");
    await loadOrderDetail(Number(row.dataset.orderId));
  });
}

async function bootstrap() {
  mount();
  try {
    await checkHealth();
    setNotice("后端服务连接正常", "success");
  } catch (error) {
    setNotice(`后端连接失败: ${error.message || "unknown"}`, "danger");
  }
  await loadOrders();
}

bootstrap();
