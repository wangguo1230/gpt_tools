const API_BASE = (import.meta.env.VITE_API_BASE || "").trim();

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : `请求失败 (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

export async function generateLink(data) {
  return request("/api/links/generate", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function querySubscriptionStatus(data) {
  return request("/api/subscription/status", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function resolveBillingCurrency(data) {
  return request("/api/regions/resolve-currency", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listOrders(params) {
  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}`.trim() !== "") {
      query.set(key, `${value}`);
    }
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request(`/api/orders${suffix}`);
}

export async function getOrderDetail(orderId, logLimit = 30) {
  return request(`/api/orders/${orderId}?log_limit=${logLimit}`);
}

export async function checkHealth() {
  return request("/api/health");
}
