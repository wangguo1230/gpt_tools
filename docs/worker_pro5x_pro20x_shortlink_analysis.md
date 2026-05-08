# Worker 端 pro5x / pro20x 短链生成分析

## 1. 调用入口

- 中心后端执行链路：`recharge/worker/executor.py` 的 `RechargeExecutor.execute()`
- 本机 Worker 执行链路：`recharge/worker/local_executor.py` 的 `LocalRechargeExecutor.execute_current_task()`
- 两条链路均调用：`checkout_service.create_checkout_from_token()`

## 2. 参数来源与覆盖顺序

1. 任务套餐来自 `task.plan_type`。
2. 套餐基础配置来自 `PlansService(...).list_all()` + `_find_plan_config(...)`。
3. 运行时覆盖来自 worker 私有配置 `runtime_config.checkout`：
   - `link_mode`
   - `billing_country`
   - `billing_currency`
4. 最终调用 `create_checkout_from_token(...)` 时传入：
   - `plan=task.plan_type`
   - `link_mode=plan_config[link_mode]`
   - `checkout_billing_country` / `checkout_billing_currency`
   - `proxy`

## 3. pro5x / pro20x 在短链生成阶段的差异

### 3.1 `create_checkout_session()` payload 差异（`upgrade.py`）

- `pro5x`：`plan_name=chatgptprolite`
- `pro20x`：
  - `link_mode=hosted` 时：`plan_name=chatgptpro`
  - 其他模式时：先 `plan_name=chatgptprolite`

### 3.2 `link_mode=long` 下 pro20x 的额外步骤

- 当 `plan=pro20x` 且不是 `short/hosted` 直接返回时，执行：
  - `update_checkout_session_plan(..., plan_name="chatgptpro", price_interval="month", seat_quantity=1)`
- `pro5x` 不会走这个 update 步骤。

### 3.3 `hosted` 特殊回退

- `pro5x` 在 hosted 模式若命中 `processor_entity` 错误，会先 `custom` 探测，再带探测出的 `processor_entity` 重试 hosted。
- `pro20x` 没有这段专门的 probe+retry 逻辑。

## 4. 返回字段使用方式

执行器统一取值策略：

- 结账 URL：优先 `stripe_checkout_url`，否则 `checkout_url`
- 短链：`checkout_short_url`，为空时回退到结账 URL

最终在任务上落库：

- `task.checkout_url`
- `task.short_url`
