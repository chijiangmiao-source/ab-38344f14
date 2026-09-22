#!/usr/bin/env bash
# verify 一次性服务入口：单元测试 -> 前端构建 -> 真实 API/HTTP 冒烟 -> Web 静态/代理冒烟。
# 任一阶段失败立即以非零退出码结束（set -e + pipefail）。
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://api:8000}"
WEB_BASE_URL="${WEB_BASE_URL:-http://web:80}"

echo "=============================================================="
echo "[1/5] Python 单元测试（求解器：环 / 同码多边 / 字典序 / 边界集）"
echo "=============================================================="
cd /workspace/api
"${PYTEST_BIN:-python}" -m pytest tests -q

echo
echo "=============================================================="
echo "[2/5] 前端依赖安装与生产构建（vite build）"
echo "=============================================================="
cd /workspace/web
npm install --no-audit --no-fund
npm run build
test -f dist/index.html

# 组件级运行时冒烟：真实渲染 SVG（布局/平行边/边界高亮逻辑）
npx esbuild scripts/ssr-smoke.mjs --bundle --platform=node --format=cjs \
  --outfile=/tmp/ssr-smoke.cjs --loader:.jsx=jsx --jsx=automatic
node /tmp/ssr-smoke.cjs

echo
echo "=============================================================="
echo "[3/5] 真实 API HTTP 冒烟（含环补全 / 同优边界集合 / 不可达 / 非法）"
echo "=============================================================="
# 等待 API 就绪（depends_on healthy 之外再做一次客户端侧等待）
for i in $(seq 1 30); do
  if curl -fsS "$API_BASE_URL/healthz" >/dev/null 2>&1; then break; fi
  sleep 1
done
python /workspace/verify/smoke_api.py "$API_BASE_URL"

echo
echo "=============================================================="
echo "[4/5] Web 真实 HTTP 冒烟（静态资源 + nginx 反代 API）"
echo "=============================================================="
for i in $(seq 1 30); do
  if curl -fsS "$WEB_BASE_URL/" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "$WEB_BASE_URL/" | grep -q '<div id="root">'
curl -fsS "$WEB_BASE_URL/api/limits" | grep -q '"max_states"'
curl -fsS "$WEB_BASE_URL/healthz" | grep -q '"status"'
echo "  web index / api proxy / healthz proxy OK"

echo
echo "=============================================================="
echo "[5/5] API 直连健康检查"
echo "=============================================================="
curl -fsS "$API_BASE_URL/healthz" | grep -q '"ok"'
echo "  direct healthz OK"

echo
echo "########## ALL VERIFY CHECKS PASSED ##########"
