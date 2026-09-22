# 真空镀膜联锁日志漏记补全

真空镀膜设备的联锁日志可能漏记阀门/泵的状态迁移。本项目给定：

- 2–80 个唯一 ASCII 状态；
- 1–300 条有向迁移，每条带**唯一标识**与**事件码**（允许成环、自环、同码多边）；
- 初态、末态；
- 1–200 个观测事件（顺序敏感）。

求解器在「每个观测恰好由一条同码迁移消费、观测之间可插入任意条漏记迁移（可绕环）」的
所有补全中：

1. **最小化**插入的漏记迁移总数；
2. 在全部最优补全里取**完整迁移标识序列字典序最小**的规范解；
3. 给出每个观测边界（0..m）在**全部最优补全**中可能出现的状态集合。

不存在可达补全或输入非法时，页面保留全部输入内容并定位原因（非法字段/行号，或首个无法
消费的观测序号与事件码）。

## 目录结构

```
api/                 FastAPI 后端（独立 Dockerfile）
  app/solver.py      核心算法（校验、双向 DP、字典序重构）
  app/main.py        /health 与 POST /api/solve
  tests/             单元/API 测试 + 700 组随机暴力对拍
web/                 React + Vite 前端（独立多阶段 Dockerfile + nginx）
  src/GraphView.jsx  SVG 图：规范路径、插入项、边界可能状态高亮
verify/              compose 中一次性 verify 服务的镜像与脚本
docker-compose.yml   api / web / verify 三服务
```

## 运行

```bash
# 可选：调整宿主机端口
cp .env.example .env

docker compose up --build
# API:  http://localhost:${API_PORT:-8000}   （/health）
# Web:  http://localhost:${WEB_PORT:-8080}   （/healthz，页面同源反代 /api）
```

端口可通过 `API_PORT` / `WEB_PORT` 环境变量（或 `.env`）配置；两个容器均带健康检查。

## 一次性校验服务 verify

重放「含环补全、同码同优边界集合、不可达请求、非法请求」四类场景，既直连 API 容器、
又经 web 容器的 nginx 反代各打一遍真实 HTTP，并执行后端单元测试、前后端构建与健康检查，
最后以退出码报告结论（verify 位于独立 profile，常规 `up` 不会触发它）：

```bash
# 自动先构建并等待 api / web 健康，再执行一次性校验，随后退出
docker compose run --build --rm verify
echo $?    # 0 表示全部通过
```

本地（无 Docker）等价验证已通过：`pytest`（16 项，含 700 组对拍，其中 254 个可行实例与
暴力枚举逐解比对）、`vite build`、对真实 uvicorn 与真实 HTTP 反代的 26 项冒烟检查。

## API

`POST /api/solve`

```json
{
  "states": ["A", "B"],
  "transitions": [
    {"id": "e_x", "source": "A", "target": "B", "code": "x"},
    {"id": "e_y", "source": "B", "target": "A", "code": "y"}
  ],
  "start": "A",
  "end": "A",
  "observations": ["x", "y", "x"]
}
```

- `200`：`inserted_count`、`canonical_sequence`（每步标注 `consumed`/`inserted` 与
  消费的观测序号）、`boundary_states`（每个边界在所有最优补全中的可能状态集合）。
- `409 {"error":{"code":"unreachable", ...}}`：无可达补全，附 `observation_index`、
  `event_code` 用于定位。
- `422 {"error":{"code":"invalid_request", ...}}`：输入非法，附具体原因。
- `GET /health`：存活探针。

## 算法说明

设 `F[b][v]` 为消费前 b 个观测后站在 v 的最少插入数；`G[b][u]` 为从边界 b 的 u 出发，
消费剩余观测并到达末态的最少插入数。每个段内所有边代价均为 1（插入计 1、消费计 0），
用以 DP 值为多种子初值的 Dijkstra 在 O((V+E) log V) 内推进，整体 O(m·(V+E) log V)。

- 最优值：`OPT = G[0][start]`。
- 边界可能状态：`v` 可在边界 b 出现 ⇔ `F[b][v] + G[b][v] == OPT`。
- 规范解：边标识按字典序编号 1..E。节点 `(b,x)` 的最优后缀长度恒为
  `L = G[b][x] + (m-b)`，其后缀键（等长 id 序列）可按
  `(首边编号, 长度 L-1 子键稠密秩)` 排序；按 L 自小到大分层做稠密秩，再贪心沿最小对
  行走，即得到完整序列字典序最小的最优解。绕环插入由 DP 自然允许（环不会进入最短路，
  同一条边可在不同段/绕环后重复消费）。

## 本地开发

```bash
# API
python3 -m venv .venv && . .venv/bin/activate
pip install -r api/requirements-test.txt
cd api && uvicorn app.main:app --reload --port 8000

# Web（dev server 默认把 /api 反代到 localhost:8000）
cd web && npm install && npm run dev
```
