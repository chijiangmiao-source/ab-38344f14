# 真空镀膜联锁日志 · 漏记迁移补全

真空镀膜设备联锁日志可能漏记阀门/泵的状态迁移。本服务在**保持观测顺序、每条观测恰由一条同码迁移消费**的约束下：

1. **精确最少化**需要补插的漏记迁移条数（不是"能到终态即可"的逐条猜补）；
2. 在全部最优补全中，按**完整迁移标识序列取字典序最小**的规范解输出；
3. 给出**每个观测边界在所有最优补全中的可能状态集合**；
4. 页面以 SVG 高亮规范路径与漏记插入项；无可达补全或输入非法时保留输入并定位原因。

## 目录结构

```
api/                FastAPI 后端（独立 Dockerfile）
  app/solver.py     核心求解器（分层展开图 + 前后向最短路径 + 字典序规范解）
  app/main.py       HTTP API：/healthz、/api/limits、/api/solve
  tests/            求解器与 API 单元测试（含 120+ 随机暴力对拍）
web/                React + Vite 前端（独立 Dockerfile，nginx 同源反代 /api）
  src/GraphSvg.jsx  SVG 状态迁移图（环、自环、平行边、边界高亮）
verify/             一次性校验服务（Dockerfile + verify.sh + HTTP 冒烟脚本）
docker-compose.yml  api / web / verify 三服务
```

## 运行

```bash
# 启动 API 与 Web（守护态）
docker compose up -d --build api web

# 访问
#   Web:        http://localhost:${WEB_PORT:-8080}
#   API 健康检查: http://localhost:${API_PORT:-8000}/healthz

# 一次性校验（单元测试 + 前端构建 + 真实 HTTP 冒烟），退出码即结论
docker compose build verify
docker compose up --exit-code-from verify verify
# 成功时 verify 容器退出码为 0，失败为非 0
```

端口可配置：复制 `.env.example` 为 `.env`，调整 `API_PORT` / `WEB_PORT`（宿主映射端口；容器内部固定 api:8000、web:80）。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 健康检查 `{"status":"ok"}` |
| GET | `/api/limits` | 输入规模约束（状态 2–80、迁移 1–300、观测 1–200） |
| POST | `/api/solve` | 求解 |

请求示例：

```json
{
  "states": ["A", "B", "C"],
  "transitions": [
    {"id": "a", "event_code": "X", "source": "A", "target": "B"},
    {"id": "loop", "event_code": "EV", "source": "B", "target": "A"},
    {"id": "b", "event_code": "Y", "source": "A", "target": "C"}
  ],
  "initial_state": "A",
  "final_state": "C",
  "observations": ["EV"]
}
```

响应（可达）：`inserted_count`（最少插入数）、`canonical_sequence`（字典序最小完整标识序列）、
`canonical_events`（每步消费的观测序号，插入步为 `null`）、`boundary_states`（边界 0..m 的可能状态）。
不可达返回 `200 {"ok":true,"feasible":false,"reason":...}`；非法输入返回
`400 {"ok":false,"error":{"message","field","index"}}`，`field/index` 供页面精确定位（如第几条迁移）。

## 算法

构造分层展开图，节点 `(相位 i, 状态 s)`，相位 i 表示已消费前 i 条观测：

- **插入边**：任意迁移 `u→v`，`(i,u)→(i,v)`，代价 1；
- **消费边**：码等于第 i+1 条观测的迁移，`(i,u)→(i+1,v)`，代价 0。

消费边严格跨相位，天然保证观测有序且每条观测恰被一条同码边消费；插入边不改相位，允许成环。
在展开图上做前向与后向 Dijkstra（0/1 权）得 `f`、`h`，最小插入数 `K = h[0][初态]`。
边界 i 的可能状态由跨层最优条件 `f[i-1][u] + h[i][v] == K` 精确给出。
字典序最小规范解利用势函数 `h·(m+1)+(m-i)` 沿最优边严格递减的性质做记忆化字典序比较
（同一条同码迁移在同一节点既可消费又可插入时，首标识相同，必须比较后继序列）。

## 本地开发（不用 Docker）

```bash
# API
cd api && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest httpx
uvicorn app.main:app --reload --port 8000

# Web（vite dev server 自动反代 /api 到 localhost:8000）
cd web && npm install && npm run dev
```
