import "./styles.css";
import {
  checkHealth,
  generateLink,
  queryBillingHistory,
  resolveBillingInvoiceFile,
  querySubscriptionStatus,
  resolveBillingCurrency,
} from "./api";
import { countryCurrencyOptions, currencyForCountry } from "./countryCurrency";

const state = {
  activeService: "subscription",
  latestSubscription: null,
  latestBilling: null,
  billingFileLoadingKey: "",
  latestTokenInput: "",
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

async function copyTextToClipboard(value) {
  const text = String(value || "").trim();
  if (!text) {
    throw new Error("没有可复制的内容");
  }
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("复制失败，请手动复制");
  }
}

function flashCopyButton(button, text = "已复制") {
  if (!button) return;
  const original = button.dataset.originalText || button.textContent || "复制";
  button.dataset.originalText = original;
  button.textContent = text;
  button.disabled = true;
  window.setTimeout(() => {
    button.textContent = original;
    button.disabled = false;
  }, 1200);
}

function switchService(next) {
  state.activeService = next;
  qsAll("[data-service-btn]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.serviceBtn === next);
  });
  qsAll("[data-service-panel]").forEach((panel) => {
    const isActive = panel.dataset.servicePanel === next;
    if (!isActive) {
      panel.hidden = true;
      panel.classList.remove("panel-enter");
      return;
    }
    panel.hidden = false;
    panel.classList.remove("panel-enter");
    void panel.offsetWidth;
    panel.classList.add("panel-enter");
  });
}

function getAuthContext() {
  const proxyEnabled = Boolean(qs("#proxy-enabled")?.checked);
  return {
    token: String(qs("#token-input")?.value || "").trim(),
    proxy: proxyEnabled ? String(qs("#proxy-input")?.value || "").trim() : "",
  };
}

function syncProxyVisibility() {
  const enabled = Boolean(qs("#proxy-enabled")?.checked);
  const proxyWrap = qs("#proxy-config");
  if (proxyWrap) proxyWrap.hidden = !enabled;
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

const PLAN_ALLOWED_LINK_MODES = Object.freeze({
  pro5x: ["short"],
  pro20x: ["short", "hosted"],
  plus: ["short", "hosted", "long"],
  team48: ["short", "hosted"],
});
const TEAM48_DEFAULT_PROMO_CODE = "THINKTECHNOLOGIESUS";
const TEAM48_DEFAULT_SEAT_QUANTITY = 2;

const LINK_MODE_LABEL_MAP = Object.freeze({
  short: "ChatGPT 短链",
  hosted: "站内长链",
  long: "站外长链",
});

const countryDisplayNames = typeof Intl !== "undefined" && Intl.DisplayNames
  ? new Intl.DisplayNames(["zh-CN"], { type: "region" })
  : null;
const currencyDisplayNames = typeof Intl !== "undefined" && Intl.DisplayNames
  ? new Intl.DisplayNames(["zh-CN"], { type: "currency" })
  : null;
const checkoutCountries = countryCurrencyOptions.map((item) => ({ code: item.code, currency: item.currency }));
const checkoutCountryByCode = new Map(checkoutCountries.map((item) => [item.code, item]));
const checkoutCurrencies = Array.from(
  new Set(checkoutCountries.map((item) => item.currency).filter(Boolean)),
).sort();

function safeDisplayName(displayNames, code) {
  if (!displayNames || !code) return code || "";
  try {
    return displayNames.of(code) || code;
  } catch {
    return code;
  }
}

function normalizeSearchText(value) {
  return String(value || "").trim().toUpperCase();
}

function parseLeadingCode(value, pattern) {
  const normalized = normalizeSearchText(value);
  const match = normalized.match(pattern);
  return match ? match[1] : normalized;
}

function countryName(code) {
  return safeDisplayName(countryDisplayNames, code);
}

function currencyName(code) {
  return safeDisplayName(currencyDisplayNames, code);
}

function formatCountryOption(option) {
  if (!option) return "";
  const parts = [option.code, countryName(option.code)];
  if (option.currency) parts.push(option.currency);
  return parts.join(" - ");
}

function formatCurrencyOption(currency) {
  if (!currency) return "";
  return `${currency} - ${currencyName(currency)}`;
}

function resolveCountryOption(value) {
  const normalized = normalizeSearchText(value);
  if (!normalized) return null;

  const leadingCode = parseLeadingCode(value, /^([A-Z0-9]{2,3})(?:\b|\s|-|\/)/);
  if (checkoutCountryByCode.has(leadingCode)) return checkoutCountryByCode.get(leadingCode);
  if (normalized.length < 2) return null;

  return checkoutCountries.find((option) => {
    const label = normalizeSearchText(formatCountryOption(option));
    return label === normalized || label.includes(normalized);
  }) || null;
}

function normalizeCountryCode(value) {
  const option = resolveCountryOption(value);
  if (option) return option.code;
  return normalizeSearchText(value);
}

function normalizeCurrencyValue(value) {
  const normalized = normalizeSearchText(value);
  if (!normalized) return "";

  const leadingCode = parseLeadingCode(value, /^([A-Z]{3})(?:\b|\s|-|\/)/);
  if (checkoutCurrencies.includes(leadingCode)) return leadingCode;
  if (normalized.length < 2) return normalized;

  const matched = checkoutCurrencies.find((currency) => {
    const label = normalizeSearchText(formatCurrencyOption(currency));
    return label === normalized || label.includes(normalized);
  });
  return matched || normalized;
}

function normalizeBillingCurrencyForCountry(country, currency) {
  if (country === "AR" && currency === "ARS") return "USD";
  return currency;
}

function normalizeTeamSeatQuantity(value) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  if (!Number.isFinite(parsed)) return TEAM48_DEFAULT_SEAT_QUANTITY;
  if (parsed < 1) return 1;
  if (parsed > 999) return 999;
  return parsed;
}

function normalizePlanValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(PLAN_ALLOWED_LINK_MODES, normalized) ? normalized : "pro5x";
}

function planLabelFromPlanType(planType) {
  const normalized = String(planType || "").trim().toLowerCase();
  if (!normalized || normalized === "unknown") return "";
  if (normalized === "free") return "FREE";
  if (normalized === "plus") return "PLUS";
  if (normalized === "team") return "TEAM";
  if (normalized === "pro" || normalized === "prolite") return "PRO";
  return normalized.toUpperCase();
}

function planLabelFromSubscriptionPlan(subscriptionPlan) {
  const normalized = String(subscriptionPlan || "").trim().toLowerCase();
  if (!normalized) return "";
  if (normalized.includes("team")) return "TEAM";
  if (normalized.includes("plus")) return "PLUS";
  if (normalized.includes("pro")) return "PRO";
  if (normalized.includes("go")) return "GO";
  if (normalized.includes("free")) return "FREE";
  return normalized.toUpperCase();
}

function hasSubscriptionHistory(payload) {
  if (!payload || typeof payload !== "object") return false;
  return Boolean(
    String(payload.subscription_start_at || "").trim()
      || String(payload.expires_at || "").trim()
      || String(payload.renews_at || "").trim()
      || String(payload.cancels_at || "").trim(),
  );
}

function normalizeLinkModeValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(LINK_MODE_LABEL_MAP, normalized) ? normalized : "short";
}

function linkModeLabel(mode) {
  return LINK_MODE_LABEL_MAP[normalizeLinkModeValue(mode)] || "支付链接";
}

function applyPlanModeRestrictions(form) {
  if (!form) return;
  const planSelect = form.querySelector("[name='plan']");
  const modeSelect = form.querySelector("[name='link_mode']");
  if (!planSelect || !modeSelect) return;

  const selectedPlan = normalizePlanValue(planSelect.value);
  const allowedModes = PLAN_ALLOWED_LINK_MODES[selectedPlan] || ["short"];
  const allowedSet = new Set(allowedModes);
  for (const option of modeSelect.options) {
    option.disabled = !allowedSet.has(option.value);
  }

  const currentMode = normalizeLinkModeValue(modeSelect.value);
  if (!allowedSet.has(currentMode)) {
    modeSelect.value = allowedModes[0];
  }

  const countryInput = form.querySelector("[name='billing_country']");
  const teamPromoInput = form.querySelector("[name='team_promo_code']");
  const teamSeatInput = form.querySelector("[name='team_seat_quantity']");
  const isTeam48 = selectedPlan === "team48";

  if (countryInput) {
    countryInput.disabled = false;
    countryInput.title = "";
  }

  if (teamPromoInput) {
    const teamPromoLabel = teamPromoInput.closest("label");
    if (teamPromoLabel) teamPromoLabel.hidden = !isTeam48;
    teamPromoInput.disabled = !isTeam48;
    teamPromoInput.required = isTeam48;
    if (isTeam48 && !String(teamPromoInput.value || "").trim()) {
      teamPromoInput.value = TEAM48_DEFAULT_PROMO_CODE;
    }
  }

  if (teamSeatInput) {
    const teamSeatLabel = teamSeatInput.closest("label");
    if (teamSeatLabel) teamSeatLabel.hidden = !isTeam48;
    teamSeatInput.disabled = !isTeam48;
    teamSeatInput.required = isTeam48;
    if (isTeam48) {
      teamSeatInput.value = String(normalizeTeamSeatQuantity(teamSeatInput.value));
    }
  }
}

function populateRegionOptions() {
  const countryList = qs("#billing-country-options");
  const currencyList = qs("#billing-currency-options");
  if (countryList) {
    countryList.innerHTML = checkoutCountries
      .map((option) => `<option value="${escapeHtml(formatCountryOption(option))}"></option>`)
      .join("");
  }
  if (currencyList) {
    currencyList.innerHTML = checkoutCurrencies
      .map((currency) => `<option value="${escapeHtml(formatCurrencyOption(currency))}"></option>`)
      .join("");
  }
}

function normalizeBillingCountryInput(input) {
  if (!input) return "";
  const option = resolveCountryOption(input.value);
  if (!option) {
    input.value = normalizeCountryCode(input.value);
    return normalizeCountryCode(input.value);
  }
  input.value = formatCountryOption(option);
  return option.code;
}

function normalizeBillingCurrencyInput(input) {
  if (!input) return "";
  const currency = normalizeCurrencyValue(input.value);
  if (!currency) {
    input.value = "";
    return "";
  }
  input.value = formatCurrencyOption(currency);
  return currency;
}

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

function renderSubscriptionLoading() {
  const box = qs("#subscription-result");
  if (!box) return;
  box.innerHTML = `
    <div class="skeleton-stack">
      <div class="skeleton-line w-40"></div>
      <div class="skeleton-line w-26"></div>
    </div>
    <div class="skeleton-grid">
      ${Array.from({ length: 8 }).map(() => '<div class="skeleton-card"></div>').join("")}
    </div>
    <div class="skeleton-line w-100"></div>
  `;
}

function renderBillingLoading() {
  const box = qs("#billing-result");
  if (!box) return;
  box.innerHTML = `
    <div class="skeleton-stack">
      <div class="skeleton-line w-30"></div>
    </div>
    <div class="billing-table-wrap">
      <table class="billing-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>金额</th>
            <th>状态</th>
            <th>描述</th>
            <th>卡信息</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${Array.from({ length: 4 })
            .map(
              () => `
            <tr>
              <td><span class="skeleton-line w-60"></span></td>
              <td><span class="skeleton-line w-40"></span></td>
              <td><span class="skeleton-line w-50"></span></td>
              <td><span class="skeleton-line w-70"></span></td>
              <td><span class="skeleton-line w-65"></span></td>
              <td><span class="skeleton-line w-55"></span></td>
            </tr>
          `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderLinkLoading() {
  const box = qs("#link-result");
  if (!box) return;
  box.innerHTML = `
    <div class="result-grid">
      ${Array.from({ length: 7 })
        .map(
          () => `
        <div class="result-row">
          <div class="result-key"><span class="skeleton-line w-50"></span></div>
          <div class="result-value"><span class="skeleton-line w-80"></span></div>
        </div>
      `,
        )
        .join("")}
    </div>
  `;
}

function renderSubscriptionResult(payload) {
  const box = qs("#subscription-result");
  if (!box) return;
  if (!payload) {
    box.innerHTML = "";
    state.latestSubscription = null;
    updateAuthDependentActions();
    return;
  }
  state.latestSubscription = payload;
  const paid = Boolean(payload.is_paid);
  const hasError = !Boolean(payload.ok) || !Boolean(payload.account_id);
  const alertTitle = hasError ? "查询失败，请检查 token 是否有效" : "查询成功，已获取订阅信息";
  const alertDesc = hasError
    ? payload.error || "无法加载账号订阅信息，请稍后重试。"
    : "可继续生成支付方式。";
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
  const latestSubscriptionPlan = String(payload.latest_subscription_plan || "").trim();
  const activeSubscription = Boolean(payload.has_active_subscription);
  const hasPreviouslyPaid = Boolean(payload.has_previously_paid_subscription);
  const recentPlanLabel = planLabelFromSubscriptionPlan(latestSubscriptionPlan);
  const currentPlanLabel = planLabelFromPlanType(planType) || "FREE";
  const hasHistorySubscription = Boolean(
    recentPlanLabel
      || hasSubscriptionHistory(payload)
      || hasPreviouslyPaid,
  );
  let historyPlanLabel = "";
  let historyPlanHint = "";
  if (!activeSubscription) {
    historyPlanLabel = recentPlanLabel || (hasHistorySubscription ? "历史订阅" : "暂无历史订阅");
    if (latestSubscriptionPlan) {
      historyPlanHint = `来源：${latestSubscriptionPlan}`;
    } else if (hasHistorySubscription) {
      historyPlanHint = "来源：无明确套餐字段，按历史订阅线索展示";
    }
  }
  const startTimeTileKey = activeSubscription ? "订阅时间" : "最近订阅时间(推断)";
  const endTimeTileKey = activeSubscription ? "订阅结束时间" : "最近订阅结束时间";
  const tiles = [
    {
      key: "当前套餐",
      value: `<span class="plan-chip">${escapeHtml(currentPlanLabel || "-")}</span>`,
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
      key: endTimeTileKey,
      value: endsAt,
      toneClass: `tile-end ${endTileToneClass}`,
      valueClass: "emphasis end-time",
    },
    { key: startTimeTileKey, value: startedAt, toneClass: "tile-neutral" },
    { key: "自动续费", value: autoRenew, toneClass: payload.has_active_subscription ? "tile-active" : "tile-neutral" },
    { key: "计费周期", value: cycle, toneClass: "tile-neutral" },
    { key: "货币单位", value: payload.billing_currency || "-", toneClass: "tile-neutral" },
    { key: "账号状态", value: accountState, toneClass: accountState === "正常" ? "tile-active" : "tile-risk" },
  ];
  if (!activeSubscription) {
    tiles.splice(1, 0, {
      key: "最近一次历史套餐",
      value: `<span class="plan-chip">${escapeHtml(historyPlanLabel || "-")}</span>`,
      isHtml: true,
      toneClass: "tile-plan",
      hint: historyPlanHint,
    });
  }
  box.innerHTML = `
    <div class="subscription-hero">
      <div>
        <p class="meta">订阅总览</p>
        <h3>${escapeHtml(paid ? "订阅中" : "未订阅")}</h3>
        <p class="hero-email">账号邮箱：${escapeHtml(accountEmail)}</p>
      </div>
      <span class="badge ${paid ? "ok" : "warn"}">${escapeHtml(currentPlanLabel || "UNKNOWN")}</span>
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
  updateAuthDependentActions();
}

function updateAuthDependentActions() {
  const { token } = getAuthContext();
  const disabled = !token;
  qsAll("[data-requires-token]").forEach((button) => {
    button.disabled = disabled;
  });
}

function renderLinkResult(payload) {
  const box = qs("#link-result");
  if (!box) return;
  if (!payload) {
    box.innerHTML = "";
    return;
  }
  const mode = normalizeLinkModeValue(payload.link_mode || "");
  const linkText = linkModeLabel(mode);
  const checkoutUrl = String(payload.checkout_url || "").trim();
  const rows = [
    { key: "订单号", value: payload.order_no || payload.order_id },
    { key: "套餐", value: payload.selected_plan },
    { key: "链接类型", value: linkText },
    {
      key: "支付链接",
      isHtml: true,
      value: checkoutUrl
        ? `
          <div class="copy-inline">
            <span class="copy-value">${escapeHtml(checkoutUrl)}</span>
            <button type="button" class="copy-btn" data-copy-text="${escapeHtml(checkoutUrl)}">复制</button>
          </div>
        `
        : "-",
    },
    { key: "地区", value: payload.billing_country },
    { key: "货币", value: payload.billing_currency },
    { key: "session_id", value: payload.checkout_session_id },
  ];
  if (normalizePlanValue(payload.selected_plan) === "team48") {
    rows.push({ key: "Team 优惠码", value: payload.team_promo_code || "-" });
    rows.push({ key: "Team 席位数", value: payload.team_seat_quantity || "-" });
  }
  if (payload.error) rows.push({ key: "提示", value: payload.error });
  box.innerHTML = `
    <div class="result-grid">
      ${rows
        .map(
          (row) => `
        <div class="result-row">
          <div class="result-key">${escapeHtml(row.key)}</div>
          <div class="result-value">${row.isHtml ? row.value : escapeHtml(row.value || "-")}</div>
        </div>
      `,
        )
        .join("")}
    </div>
  `;
}

function billingFileKey(invoice, index, fileType) {
  return `${fileType}:${index}:${String(invoice?.id || invoice?.slug || "").trim()}`;
}

function renderBillingResult(payload) {
  const box = qs("#billing-result");
  if (!box) return;
  if (!payload) {
    box.innerHTML = "";
    state.latestBilling = null;
    state.billingFileLoadingKey = "";
    return;
  }

  state.latestBilling = payload;
  const invoices = Array.isArray(payload.invoices) ? payload.invoices : [];
  const notice = String(payload.notice || "").trim();
  const hasError = !Boolean(payload.ok);
  const summary = `${invoices.length} 条账单记录`;

  if (!invoices.length) {
    box.innerHTML = `
      <div class="billing-head">
        <h4>历史账单查询</h4>
        <span>${escapeHtml(summary)}</span>
      </div>
      <p class="placeholder">${escapeHtml(notice || (hasError ? "账单查询失败" : "暂无账单记录"))}</p>
      ${hasError && payload.error ? `<p class="warn-text">错误：${escapeHtml(payload.error)}</p>` : ""}
    `;
    return;
  }

  const rowsHtml = invoices
    .map((invoice, index) => {
      const slug = String(invoice.slug || "").trim();
      const hosted = String(invoice.hosted_invoice_url || "").trim();
      const invoiceUrl = String(invoice.invoice_pdf_url || "").trim();
      const receiptUrl = String(invoice.receipt_pdf_url || "").trim();
      const invoiceLoading = state.billingFileLoadingKey === billingFileKey(invoice, index, "invoice");
      const receiptLoading = state.billingFileLoadingKey === billingFileKey(invoice, index, "receipt");

      const invoiceAction = invoiceUrl
        ? `<a class="billing-link" href="${escapeHtml(invoiceUrl)}" target="_blank" rel="noopener noreferrer">打开发票</a>`
        : `<button type="button" class="billing-btn" data-file-type="invoice" data-index="${index}" ${slug ? "" : "disabled"}>${invoiceLoading ? "获取中..." : "获取发票"}</button>`;

      const receiptAction = receiptUrl
        ? `<a class="billing-link" href="${escapeHtml(receiptUrl)}" target="_blank" rel="noopener noreferrer">打开收据</a>`
        : `<button type="button" class="billing-btn" data-file-type="receipt" data-index="${index}" ${slug ? "" : "disabled"}>${receiptLoading ? "获取中..." : "获取收据"}</button>`;

      const hostedAction = hosted
        ? `<a class="billing-link muted" href="${escapeHtml(hosted)}" target="_blank" rel="noopener noreferrer">账单详情</a>`
        : '<span class="billing-muted">-</span>';

      return `
        <tr>
          <td>${escapeHtml(invoice.date || "-")}</td>
          <td>${escapeHtml(invoice.amount || "-")}</td>
          <td>${escapeHtml(invoice.status || "-")}</td>
          <td>${escapeHtml(invoice.description || "-")}</td>
          <td>${escapeHtml(invoice.card || "-")}</td>
          <td>
            <div class="billing-actions-cell">
              ${invoiceAction}
              ${receiptAction}
              ${hostedAction}
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  box.innerHTML = `
    <div class="billing-head">
      <h4>历史账单查询</h4>
      <span>${escapeHtml(summary)}</span>
    </div>
    <div class="billing-table-wrap">
      <table class="billing-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>金额</th>
            <th>状态</th>
            <th>描述</th>
            <th>卡信息</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
    ${notice ? `<p class="billing-notice">${escapeHtml(notice)}</p>` : ""}
  `;
}

async function queryBillingHistoryWithInput({ button = null } = {}) {
  const { token, proxy } = getAuthContext();
  if (!token) {
    setNotice("请先输入 token", "danger");
    return null;
  }
  if (button) setButtonLoading(button, true, "查询中...");
  renderBillingLoading();
  try {
    const payload = await queryBillingHistory({ token, proxy });
    renderBillingResult(payload);
    setNotice("历史账单查询成功", "success");
    return payload;
  } catch (error) {
    renderBillingResult({
      ok: false,
      invoices: [],
      notice: error.message || "历史账单查询失败",
      error: error.message || "历史账单查询失败",
    });
    setNotice(error.message || "历史账单查询失败", "danger");
    return null;
  } finally {
    if (button) setButtonLoading(button, false);
    updateAuthDependentActions();
  }
}

async function prepareInvoiceFile(index, fileType) {
  const invoices = Array.isArray(state.latestBilling?.invoices) ? state.latestBilling.invoices : [];
  const invoice = invoices[index];
  if (!invoice) return;
  const slug = String(invoice.slug || "").trim();
  if (!slug) {
    setNotice(fileType === "receipt" ? "该账单没有收据标识" : "该账单没有发票标识", "danger");
    return;
  }
  const key = billingFileKey(invoice, index, fileType);
  state.billingFileLoadingKey = key;
  renderBillingResult(state.latestBilling);
  try {
    const { proxy } = getAuthContext();
    const payload = await resolveBillingInvoiceFile({
      slug,
      file_type: fileType,
      proxy,
    });
    const resolvedUrl = String(payload.url || "").trim();
    if (!resolvedUrl) {
      throw new Error("未获取到可用文件链接");
    }
    if (fileType === "receipt") {
      invoice.receipt_pdf_url = resolvedUrl;
    } else {
      invoice.invoice_pdf_url = resolvedUrl;
    }
    renderBillingResult(state.latestBilling);
    setNotice(fileType === "receipt" ? "收据链接已准备好" : "发票链接已准备好", "success");
  } catch (error) {
    renderBillingResult(state.latestBilling);
    setNotice(error.message || "账单文件链接获取失败", "danger");
  } finally {
    state.billingFileLoadingKey = "";
    renderBillingResult(state.latestBilling);
  }
}


async function autoResolveCurrency(form, { silent = false } = {}) {
  const auth = getAuthContext();
  const countryInput = form.querySelector("[name='billing_country']");
  const currencyInput = form.querySelector("[name='billing_currency']");

  const country = normalizeBillingCountryInput(countryInput);
  const currency = normalizeCurrencyValue(String(currencyInput?.value || ""));
  if (!country) return null;

  const mappedCurrency = String(currencyForCountry(country) || "").trim().toUpperCase();
  const localCurrency = normalizeBillingCurrencyForCountry(country, mappedCurrency);
  if (localCurrency || currency) {
    const resolvedCurrency = localCurrency || normalizeBillingCurrencyForCountry(country, currency);
    if (currencyInput) currencyInput.value = resolvedCurrency ? formatCurrencyOption(resolvedCurrency) : "";
    if (!silent && resolvedCurrency !== currency) {
      setNotice(`已自动匹配货币：${country} -> ${resolvedCurrency}`, "success");
    }
    return {
      ok: true,
      billing_country: country,
      billing_currency: resolvedCurrency,
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
  if (countryInput) normalizeBillingCountryInput(countryInput);
  if (currencyInput) {
    const resolvedCurrency = normalizeBillingCurrencyForCountry(
      String(payload.billing_country || "").trim().toUpperCase(),
      String(payload.billing_currency || "").trim().toUpperCase(),
    );
    currencyInput.value = resolvedCurrency ? formatCurrencyOption(resolvedCurrency) : "";
  }
  if (!silent) setNotice(`已自动匹配货币：${payload.billing_country} -> ${payload.billing_currency}`, "success");
  return payload;
}

async function querySubscriptionWithInput({ button = null, loadingText = "查询中...", successNotice = "订阅状态查询成功" } = {}) {
  const { token, proxy } = getAuthContext();
  if (!token) {
    setNotice("请先输入 token", "danger");
    return null;
  }
  state.latestTokenInput = token;
  if (button) setButtonLoading(button, true, loadingText);
  renderSubscriptionLoading();
  try {
    const payload = await querySubscriptionStatus({ token, proxy });
    renderSubscriptionResult(payload);
    setNotice(successNotice, "success");
    return payload;
  } catch (error) {
    renderSubscriptionResult({ error: error.message || "订阅状态查询失败" });
    setNotice(error.message || "订阅状态查询失败", "danger");
    return null;
  } finally {
    if (button) setButtonLoading(button, false);
    updateAuthDependentActions();
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
          <div class="brand-sub">Token管理 · 订阅状态 · 支付方式</div>
        </div>
      </div>
      <div class="notice" id="notice" data-tone="neutral">正在初始化...</div>
    </header>

    <main class="layout">
      <section class="workspace-card">
        <div class="workspace-head">
          <h2>数据中心</h2>
          <p>三个功能页签：订阅查询、历史账单查询、生成支付链接。Token 与代理保持不变，仅下方内容切换。</p>
        </div>

        <nav class="service-tabs">
          <button data-service-btn="subscription" class="active">订阅查询</button>
          <button data-service-btn="billing">历史账单查询</button>
          <button data-service-btn="payment">生成支付链接</button>
        </nav>

        <section class="hint-card">
          <h3>如何获取 Token 数据？</h3>
          <ul>
            <li><b>第一步：</b>先登录 <a href="https://chatgpt.com" target="_blank" rel="noopener noreferrer">https://chatgpt.com</a></li>
            <li><b>第二步：</b>访问 <a href="https://chatgpt.com/api/auth/session" target="_blank" rel="noopener noreferrer">https://chatgpt.com/api/auth/session</a>，复制页面 JSON。</li>
          </ul>
        </section>

        <section class="auth-card">
          <label class="auth-label">请输入复制的 Session JSON</label>
          <textarea id="token-input" rows="6" placeholder="粘贴从 /api/auth/session 复制的完整 Session JSON"></textarea>
          <label class="proxy-toggle" for="proxy-enabled">
            <input id="proxy-enabled" type="checkbox" />
            启用代理
          </label>
          <div id="proxy-config" hidden>
            <label class="proxy-row" for="proxy-input">代理地址 (HTTP)</label>
            <input id="proxy-input" type="text" placeholder="http://user:pass@127.0.0.1:10808" />
            <p class="proxy-help">支持 HTTP 代理，支持用户名密码，例如：http://user:pass@host:port</p>
          </div>
        </section>

        <section data-service-panel="subscription" class="service-panel">
          <div class="service-panel-head service-panel-head-center">
            <button type="button" id="query-subscription-btn" data-requires-token>查询订阅</button>
          </div>
          <article class="result-box result-box-plain" id="subscription-result"></article>
        </section>

        <section data-service-panel="billing" class="service-panel" hidden>
          <div class="service-panel-head service-panel-head-center">
            <button type="button" id="query-billing-btn" data-requires-token>查询历史账单</button>
          </div>
          <article class="result-box result-box-plain billing-result" id="billing-result"></article>
        </section>

        <section data-service-panel="payment" class="service-panel" hidden>
          <div class="service-panel-head">
            <h3>生成支付链接</h3>
          </div>
          <form id="link-form" class="form-grid">
            <label>
              套餐
              <select name="plan">
                <option value="pro5x">Pro5x</option>
                <option value="pro20x">Pro20x</option>
                <option value="plus">PLUS</option>
                <option value="team48">Team 48 个月</option>
              </select>
            </label>
            <label>
              默认返回链接
              <select name="link_mode">
                <option value="short">ChatGPT 短链</option>
                <option value="hosted">站内长链</option>
                <option value="long">站外长链</option>
              </select>
            </label>
            <label>
              地区 (Country)
              <input type="text" name="billing_country" maxlength="64" list="billing-country-options" placeholder="支持搜索，例如 US / 美国 / 菲律宾" />
            </label>
            <label>
              货币 (Currency)
              <input type="text" name="billing_currency" maxlength="32" list="billing-currency-options" placeholder="自动带出，可搜索或手动改" />
            </label>
            <label hidden>
              Team 优惠码
              <input type="text" name="team_promo_code" maxlength="128" placeholder="例如 THINKTECHNOLOGIESUS" />
            </label>
            <label hidden>
              Team 席位数
              <input type="number" name="team_seat_quantity" min="1" max="999" step="1" value="2" />
            </label>
            <div class="form-actions">
              <button id="generate-link-btn" type="submit" data-requires-token>生成支付方式</button>
            </div>
          </form>
          <datalist id="billing-country-options"></datalist>
          <datalist id="billing-currency-options"></datalist>
          <article class="result-box result-box-plain" id="link-result"></article>
        </section>

      </section>
    </main>
  `;

  qsAll("[data-service-btn]").forEach((button) => {
    button.addEventListener("click", () => switchService(button.dataset.serviceBtn));
  });

  qs("#query-subscription-btn").addEventListener("click", async () => {
    const button = qs("#query-subscription-btn");
    await querySubscriptionWithInput({
      button,
      loadingText: "查询中...",
      successNotice: "订阅状态查询成功",
    });
  });

  qs("#query-billing-btn").addEventListener("click", async () => {
    const button = qs("#query-billing-btn");
    await queryBillingHistoryWithInput({ button });
  });
  qs("#link-result").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-copy-text]");
    if (!button) return;
    const text = String(button.getAttribute("data-copy-text") || "").trim();
    if (!text) {
      setNotice("没有可复制的链接", "danger");
      return;
    }
    try {
      await copyTextToClipboard(text);
      flashCopyButton(button, "已复制");
      setNotice("支付链接已复制", "success");
    } catch (error) {
      setNotice(error.message || "复制失败，请手动复制", "danger");
    }
  });
  qs("#billing-result").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-file-type][data-index]");
    if (!button) return;
    const fileType = String(button.dataset.fileType || "").trim().toLowerCase();
    const index = Number.parseInt(String(button.dataset.index || ""), 10);
    if (!Number.isInteger(index) || index < 0) return;
    if (fileType !== "invoice" && fileType !== "receipt") return;
    await prepareInvoiceFile(index, fileType);
  });

  const tokenInput = qs("#token-input");
  const proxyEnabledInput = qs("#proxy-enabled");
  if (tokenInput) {
    tokenInput.addEventListener("input", () => {
      updateAuthDependentActions();
    });
  }
  if (proxyEnabledInput) {
    proxyEnabledInput.addEventListener("change", () => {
      syncProxyVisibility();
    });
  }
  syncProxyVisibility();
  updateAuthDependentActions();
  switchService(state.activeService);

  const linkForm = qs("#link-form");
  populateRegionOptions();
  applyPlanModeRestrictions(linkForm);

  const planInput = linkForm.querySelector("[name='plan']");
  planInput.addEventListener("change", () => {
    applyPlanModeRestrictions(linkForm);
  });

  const countryInput = linkForm.querySelector("[name='billing_country']");
  const currencyInput = linkForm.querySelector("[name='billing_currency']");
  const teamPromoInput = linkForm.querySelector("[name='team_promo_code']");
  const teamSeatInput = linkForm.querySelector("[name='team_seat_quantity']");

  countryInput.addEventListener("change", async () => {
    try {
      await autoResolveCurrency(linkForm, { silent: false });
    } catch (error) {
      setNotice(error.message || "自动识别货币失败", "danger");
    }
  });
  countryInput.addEventListener("blur", () => {
    normalizeBillingCountryInput(countryInput);
  });
  currencyInput.addEventListener("blur", () => {
    normalizeBillingCurrencyInput(currencyInput);
  });

  linkForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const auth = getAuthContext();
    if (!auth.token) {
      setNotice("请先在上方填写 token", "danger");
      return;
    }

    const submitButton = qs("#generate-link-btn");
    const form = new FormData(event.currentTarget);
    const plan = normalizePlanValue(String(form.get("plan") || "pro5x"));
    const modeRaw = normalizeLinkModeValue(String(form.get("link_mode") || "short"));
    const allowedModes = PLAN_ALLOWED_LINK_MODES[plan] || ["short"];
    const linkMode = allowedModes.includes(modeRaw) ? modeRaw : allowedModes[0];
    let billingCountry = normalizeCountryCode(String(form.get("billing_country") || ""));
    let billingCurrency = normalizeBillingCurrencyForCountry(
      billingCountry,
      normalizeCurrencyValue(String(form.get("billing_currency") || "")),
    );
    const payload = {
      token: auth.token,
      proxy: auth.proxy,
      plan,
      link_mode: linkMode,
      billing_country: billingCountry,
      billing_currency: billingCurrency,
    };
    if (plan === "team48") {
      const promoCode = String(form.get("team_promo_code") || "").trim() || TEAM48_DEFAULT_PROMO_CODE;
      const seatQuantity = normalizeTeamSeatQuantity(form.get("team_seat_quantity"));
      payload.team_promo_code = promoCode;
      payload.team_seat_quantity = seatQuantity;
      if (teamPromoInput) teamPromoInput.value = promoCode;
      if (teamSeatInput) teamSeatInput.value = String(seatQuantity);
    }

    applyPlanModeRestrictions(linkForm);
    if (countryInput && payload.billing_country) {
      const matched = checkoutCountryByCode.get(payload.billing_country);
      countryInput.value = matched ? formatCountryOption(matched) : payload.billing_country;
    }
    if (currencyInput) {
      currencyInput.value = payload.billing_currency ? formatCurrencyOption(payload.billing_currency) : "";
    }

    if (payload.billing_country && !payload.billing_currency) {
      try {
        const resolved = await autoResolveCurrency(linkForm, { silent: true });
        if (resolved?.billing_currency) {
          payload.billing_currency = String(resolved.billing_currency || "").trim().toUpperCase();
          if (currencyInput) currencyInput.value = formatCurrencyOption(payload.billing_currency);
        }
      } catch {
        // keep user input
      }
    }

    setButtonLoading(submitButton, true, "生成中...");
    renderLinkLoading();
    try {
      const result = await generateLink(payload);
      renderLinkResult(result);
      setNotice(`支付方式生成成功：${linkModeLabel(result.link_mode || payload.link_mode)}`, "success");
    } catch (error) {
      renderLinkResult({ error: error.message || "支付方式生成失败" });
      setNotice(error.message || "支付方式生成失败", "danger");
    } finally {
      setButtonLoading(submitButton, false);
      updateAuthDependentActions();
    }
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
}

bootstrap();
