import "./styles.css";
import {
  checkHealth,
  generateLink,
  getOrderDetail,
  listOrders,
  resolveBillingCurrency,
} from "./api";
import { currencyForCountry } from "./countryCurrency";

const state = {
  activeTab: "links",
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
  el.textContent = message;
  el.dataset.tone = tone;
}

function switchTab(nextTab) {
  state.activeTab = nextTab;
  qsAll("[data-tab-btn]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tabBtn === nextTab);
  });
  qsAll("[data-tab-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== nextTab;
  });
}

function qsAll(selector) {
  return Array.from(document.querySelectorAll(selector));
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

function renderLinkResult(payload) {
  const block = qs("#link-result");
  if (!payload) {
    block.innerHTML = "<p class=\"placeholder\">等待生成结果...</p>";
    return;
  }

  const paymentMethods = payload?.payment_methods || {};
  const rows = [
    ["order_id", payload.order_id],
    ["order_no", payload.order_no],
    ["selected_plan", payload.selected_plan],
    ["link_mode", payload.link_mode],
    ["payment.short", paymentMethods.short],
    ["payment.hosted", paymentMethods.hosted],
    ["payment.stripe", paymentMethods.stripe],
    ["checkout_short_url", payload.checkout_short_url],
    ["checkout_url", payload.checkout_url],
    ["stripe_checkout_url", payload.stripe_checkout_url],
    ["checkout_session_id", payload.checkout_session_id],
    ["processor_entity", payload.processor_entity],
    ["billing_country", payload.billing_country],
    ["billing_currency", payload.billing_currency],
    ["billing_source", payload.billing_source],
    ["source", payload.source],
  ];
  if (payload.error) {
    rows.push(["error", payload.error]);
  }

  block.innerHTML = `
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

  summary.textContent = `共 ${payload?.total ?? 0} 条，当前 ${items.length} 条`;

  if (!items.length) {
    tbody.innerHTML = "<tr><td colspan=\"6\" class=\"placeholder\">暂无数据</td></tr>";
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
  if (!payload?.item) {
    box.innerHTML = "<p class=\"placeholder\">点击列表行查看订单详情</p>";
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
  detailBox.innerHTML = "<p class=\"placeholder\">正在加载详情...</p>";
  try {
    const payload = await getOrderDetail(orderId, 40);
    renderOrderDetail(payload);
  } catch (error) {
    renderOrderDetail(null);
    setNotice(error.message || "加载订单详情失败", "danger");
  }
}

async function autoResolveCurrency(form, { silent = false } = {}) {
  const token = String(form.querySelector("[name='token']")?.value || "").trim();
  const billingCountryInput = form.querySelector("[name='billing_country']");
  const billingCurrencyInput = form.querySelector("[name='billing_currency']");
  const proxyInput = form.querySelector("[name='proxy']");
  const country = String(billingCountryInput?.value || "").trim().toUpperCase();
  const currency = String(billingCurrencyInput?.value || "").trim().toUpperCase();
  const proxy = String(proxyInput?.value || "").trim();

  if (!country) return null;

  const localCurrency = String(currencyForCountry(country) || "").trim().toUpperCase();
  if (localCurrency) {
    if (billingCountryInput) billingCountryInput.value = country;
    if (billingCurrencyInput) billingCurrencyInput.value = localCurrency;
    if (!silent && currency !== localCurrency) {
      setNotice(`已自动匹配货币：${country} -> ${localCurrency}（来源: worker_country_map）`, "success");
    }
    return {
      ok: true,
      billing_country: country,
      billing_currency: localCurrency,
      source: "worker_country_map",
      error: "",
    };
  }

  if (!token) {
    if (!silent) {
      setNotice("该地区未命中本地映射，请输入 token 后在线解析货币", "danger");
    }
    return null;
  }

  const payload = await resolveBillingCurrency({
    token,
    billing_country: country,
    billing_currency: currency,
    proxy,
  });
  if (billingCountryInput) billingCountryInput.value = String(payload.billing_country || "").toUpperCase();
  if (billingCurrencyInput) billingCurrencyInput.value = String(payload.billing_currency || "").toUpperCase();
  if (!silent) {
    const source = payload.source ? `（来源: ${payload.source}）` : "";
    setNotice(
      `已自动匹配货币：${payload.billing_country || country} -> ${payload.billing_currency || "-"} ${source}`.trim(),
      "success",
    );
  }
  return payload;
}

function mount() {
  const app = qs("#app");
  app.innerHTML = `
    <div class="aurora"></div>
    <main class="page">
      <header class="hero">
        <div>
          <p class="kicker">Generated Workspace Tool</p>
          <h1>GPT Tools</h1>
          <p class="sub">输入 token + 地区自动识别货币，一键生成 Pro / Plus 三种支付方式（short / hosted / stripe）。</p>
        </div>
        <div class="status" id="notice" data-tone="neutral">正在初始化...</div>
      </header>

      <section class="tabs">
        <button data-tab-btn="links" class="active">支付方式生成</button>
        <button data-tab-btn="orders">订单查询</button>
      </section>

      <section data-tab-panel="links" class="panel">
        <form id="link-form" class="form-grid">
          <label>
            Token
            <textarea name="token" rows="5" placeholder="粘贴 access_token 或 Bearer ..." required></textarea>
          </label>
          <label>
            套餐
            <select name="plan">
              <option value="pro">Pro</option>
              <option value="plus">Plus</option>
            </select>
          </label>
          <label>
            默认返回支付方式
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
          <label>
            Proxy (可选)
            <input type="text" name="proxy" placeholder="http://127.0.0.1:7897" />
          </label>
          <div class="form-actions">
            <button id="generate-link-btn" type="submit">生成支付方式</button>
          </div>
        </form>

        <article class="result-box" id="link-result">
          <p class="placeholder">等待生成结果...</p>
        </article>
      </section>

      <section data-tab-panel="orders" class="panel" hidden>
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
    </main>
  `;

  qsAll("[data-tab-btn]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tabBtn));
  });

  const linkForm = qs("#link-form");
  const countryInput = linkForm.querySelector("[name='billing_country']");
  const tokenInput = linkForm.querySelector("[name='token']");

  countryInput.addEventListener("change", async () => {
    try {
      await autoResolveCurrency(linkForm, { silent: false });
    } catch (error) {
      setNotice(error.message || "自动识别货币失败", "danger");
    }
  });

  tokenInput.addEventListener("blur", async () => {
    if (!String(countryInput.value || "").trim()) return;
    try {
      await autoResolveCurrency(linkForm, { silent: true });
    } catch {
      // 静默失败：提交时会再次校验
    }
  });

  linkForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const submitButton = qs("#generate-link-btn");
    const billingCountryInput = linkForm.querySelector("[name='billing_country']");
    const billingCurrencyInput = linkForm.querySelector("[name='billing_currency']");
    const payload = {
      token: String(form.get("token") || "").trim(),
      plan: String(form.get("plan") || "pro").trim().toLowerCase(),
      link_mode: String(form.get("link_mode") || "short").trim(),
      billing_country: String(form.get("billing_country") || "").trim().toUpperCase(),
      billing_currency: String(form.get("billing_currency") || "").trim().toUpperCase(),
      proxy: String(form.get("proxy") || "").trim(),
    };

    if (!payload.token) {
      setNotice("请先输入 token", "danger");
      return;
    }
    if (payload.billing_country && !payload.billing_currency) {
      try {
        const resolved = await autoResolveCurrency(linkForm, { silent: false });
        if (resolved) {
          payload.billing_country = String(resolved.billing_country || "").trim().toUpperCase();
          payload.billing_currency = String(resolved.billing_currency || "").trim().toUpperCase();
          if (billingCountryInput) billingCountryInput.value = payload.billing_country;
          if (billingCurrencyInput) billingCurrencyInput.value = payload.billing_currency;
        }
      } catch (error) {
        setNotice(error.message || "自动识别货币失败", "danger");
        return;
      }
    }

    setButtonLoading(submitButton, true, "生成中...");
    renderLinkResult(null);

    try {
      const result = await generateLink(payload);
      renderLinkResult(result);
      setNotice("支付方式生成成功", "success");
    } catch (error) {
      setNotice(error.message || "支付方式生成失败", "danger");
      renderLinkResult({ error: error.message || "支付方式生成失败" });
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
