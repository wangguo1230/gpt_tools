# GPT Tools（完全独立版）

`gpt_tools` 现在是可抽离的完整工具，不依赖当前仓库任何业务模块。

## 能力

1. 输入 `token + 地区`，自动解析 Checkout 货币。
2. 支持 `Pro5x / Pro20x / PLUS / Team 48 个月`，按选择生成单一支付方式：
   - `short`（ChatGPT 短链）
   - `hosted`（站内长链，pay.openai Hosted）
   - `long`（站外长链，checkout.stripe）
   - 约束：`Pro5x` 仅支持 `short`，`Pro20x / PLUS / Team 48 个月` 支持三种模式
   - `Team 48 个月` 默认使用优惠码 `THINKTECHNOLOGIESUS`，并支持前端自定义优惠码与席位数
   - `Team 48 个月` 的地区与货币按前端选择生成，不再强制固定美国/美元
   - `Team 48 个月` 在 `hosted` 模式下采用“短链会话转长链”方式生成（兼容性更好）
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
    "plan":"pro5x",
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

## GitHub 自动化构建 + Docker Compose 部署

已新增：

- `.github/workflows/publish-ghcr.yml`
- `docker-compose.yml`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `backend/Dockerfile`

### 自动构建行为

触发条件：

- `push` 到 `main`
- 手动触发 `workflow_dispatch`

执行流程：

1. 自动构建并推送后端镜像到 GHCR：`ghcr.io/<owner>/<repo>/gpt-tools-backend`
2. 自动构建并推送前端镜像到 GHCR：`ghcr.io/<owner>/<repo>/gpt-tools-frontend`

说明：

- 该流程不做服务器 SSH 部署，不需要配置 `DEPLOY_*` secrets
- 发布 GHCR 使用仓库内置 `GITHUB_TOKEN`

### 服务器使用 Docker Compose 部署

在服务器部署目录准备 `.env`（示例）：

```bash
BACKEND_IMAGE=ghcr.io/wangguo1230/gpt_tools/gpt-tools-backend:latest
FRONTEND_IMAGE=ghcr.io/wangguo1230/gpt_tools/gpt-tools-frontend:latest
FRONTEND_PORT=8080
NGINX_PORT=80
BACKEND_PORT=18777
GPT_TOOLS_CORS_ORIGINS=http://localhost:8080
GPT_TOOLS_DATABASE_URL=sqlite:////app/data/gpt_tools.db
```

然后执行：

```bash
docker compose --env-file .env pull
docker compose --env-file .env up -d --remove-orphans
```
