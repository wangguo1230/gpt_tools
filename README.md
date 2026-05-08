# GPT Tools（完全独立版）

`generated/gpt_tools` 现在是可抽离的完整工具，不依赖当前仓库任何业务模块。

## 能力

1. 输入 `token + 地区`，自动解析 Checkout 货币。
2. 支持 `Pro / Plus`，一次生成三种支付方式：
   - `short`（ChatGPT checkout）
   - `hosted`（pay.openai）
   - `stripe`（checkout.stripe）
3. 查询本工具自身订单（生成记录 + 日志）。

## 独立性说明

- 后端不再 import `openai_pool_orchestrator`。
- 后端自带短链生成逻辑（调用 ChatGPT Checkout API + Stripe init）。
- 后端自带数据库模型与持久化（默认 SQLite）。
- 前端仅调用本工具后端 API。

## 目录

```text
generated/gpt_tools/
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
cd generated/gpt_tools/backend
pip install -r requirements.txt
python run.py
```

默认监听：`http://127.0.0.1:18777`

## 前端启动

```bash
cd generated/gpt_tools/frontend
npm install
npm run dev
```

默认访问：`http://127.0.0.1:5173`

## API

- `POST /api/links/generate`
- `POST /api/regions/resolve-currency`
- `GET /api/orders`
- `GET /api/orders/{order_id}`

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
