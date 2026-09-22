# verify 一次性服务镜像：含 Python（单元测试/冒烟）与 Node（前端构建）。
FROM node:20-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Python 依赖（API 运行依赖 + 测试）
COPY api/requirements.txt /workspace/api/requirements.txt
RUN python3 -m pip install --break-system-packages -q -r /workspace/api/requirements.txt pytest httpx

# 源码
COPY api /workspace/api
COPY web /workspace/web
COPY verify /workspace/verify
RUN chmod +x /workspace/verify/verify.sh

# Web 依赖预先安装（利用层缓存）
RUN cd /workspace/web && npm install --no-audit --no-fund

ENV PYTEST_BIN=python3

CMD ["/workspace/verify/verify.sh"]
