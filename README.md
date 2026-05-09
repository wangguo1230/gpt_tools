# GPT Tools（完全独立版）

`gpt_tools` 现在是可抽离的完整工具，不依赖当前仓库任何业务模块。

## 能力

1. 输入 `token + 地区`，自动解析 Checkout 货币。
2. 支持 `Pro / Plus`，一次生成三种支付方式：
   - `short`（ChatGPT checkout）
   - `hosted`（pay.openai）
   - `stripe`（checkout.stripe）
3. 查询 `me + 订阅` 关键字段（`/backend-api/me`、`/backend-api/accounts/check`、`/backend-api/payments/customer_portal` 聚合）。
4. 查询本工具自身订单（生成记录 + 日志）。

## 独立性说明

- 后端不再 import `openai_pool_orchestrator`。
- 后端自带短链生成逻辑（调用 ChatGPT Checkout API + Stripe init）。
- 后端自带数据库模型与持久化（默认 SQLite）。
- 前端仅调用本工具后端 API。

## 目录

```text
gpt_tools/
  backend/
    app/
      main.py
      database.py
      models.py
      schemas.py
      services/
        checkout.py
        checkout_client.py
        orders.py
        db.py
    requirements.txt
    run.py
    data/           # 默认自动创建
  frontend/
    index.html
    vite.config.js
    package.json
    src/
      api.js
      main.js
      styles.css
  docs/
    worker_pro5x_pro20x_shortlink_analysis.md
```

## 后端启动

```bash
cd gpt_tools/backend
pip install -r requirements.txt
python run.py
```

默认监听：`http://127.0.0.1:18777`

## 后端启动（uv 推荐）

```bash
cd gpt_tools
uv sync --project backend
uv run --project backend python backend/run.py
```

默认监听：`http://127.0.0.1:18777`

## 前端启动

```bash
cd gpt_tools/frontend
npm install
npm run dev
```

默认访问：`http://127.0.0.1:5173`

## VSCode 一键启动

已提供：
- `.vscode/tasks.json`
- `.vscode/launch.json`

用法：
1. 打开 VSCode `运行和调试`。
2. 选择 `GPT Tools: 一键启动前后端`。
3. 或在 `Terminal -> Run Task` 里执行 `dev: all`。

## API

- `POST /api/subscription/status`
- `POST /api/token/profile`
- `POST /api/links/generate`
- `POST /api/regions/resolve-currency`
- `GET /api/orders`
- `GET /api/orders/{order_id}`

### 查询订阅状态示例

```bash
curl -X POST "http://127.0.0.1:18777/api/subscription/status" \
  -H "Content-Type: application/json" \
  -d '{
    "token":"Bearer xxx",
    "proxy":"http://127.0.0.1:10808"
  }'
```

### 订阅渠道字段说明

- `purchase_origin_platform`：优先取 `accounts/check` 的 `last_active_subscription.purchase_origin_platform`
- `channel_guess`：渠道归类结果，当前包含 `google_play_like / apple_iap_like / web_stripe_like / not_purchased / active_unknown / paid_unknown`
- `channel_confidence`：置信度（`high / medium / low`）

### 查询 me + 订阅字段示例

```bash
curl -X POST "http://127.0.0.1:18777/api/token/profile" \
  -H "Content-Type: application/json" \
  -d '{
    "token":"Bearer xxx",
    "proxy":"http://127.0.0.1:10808"
  }'
```

### 生成短链示例

```bash
curl -X POST "http://127.0.0.1:18777/api/links/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "token":"Bearer xxx",
    "plan":"pro",
    "link_mode":"short",
    "billing_country":"US"
  }'
```

## 环境变量

- `GPT_TOOLS_DATABASE_URL`：数据库连接串（默认本地 SQLite 文件）
- `GPT_TOOLS_BACKEND_HOST`：后端 host（默认 `127.0.0.1`）
- `GPT_TOOLS_BACKEND_PORT`：后端端口（默认 `18777`）
- `GPT_TOOLS_BACKEND_RELOAD`：是否热更新（`1/true` 开启）
- `GPT_TOOLS_CORS_ORIGINS`：允许跨域来源，逗号分隔
- `VITE_API_TARGET`：前端 dev 代理目标（默认 `http://127.0.0.1:18777`）
- `VITE_API_BASE`：前端请求前缀（可选）
