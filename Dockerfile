# syntax=docker/dockerfile:1.7
#
# CER-Intent: intent manager and studio, RFC 9543 slice controller, dashboards (port 5000);
# MCP tools on port 8765 (python -m cer_intent.mcp --transport streamable-http --host 0.0.0.0).
#
#   docker build -t cer-intent .
#       the service, for a TeraFlowSDN of your own (compose.yaml, deploy/helm/cer-intent)
#
#   docker build --target demo --build-context fork=../teraflowsdn -t cer-intent-demo .
#       plus two emulated radios and a TeraFlowSDN stand-in with the fork's Ceragon driver and
#       handler (compose.demo.yaml); deploy/get-sources.sh fetches ../teraflowsdn
#
# Runtime state (intents, audit, the auto-approval settings an admin changed) lives in
# /app/data: mount a volume there. Reference data the image carries is copied in on first start.

ARG PYTHON=3.11

FROM python:${PYTHON}-slim AS base
ARG VERSION=0.2.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ceragon_tfs_adapter/ ceragon_tfs_adapter/
RUN pip install ./ceragon_tfs_adapter

RUN useradd --uid 10001 --gid 0 --no-create-home --home-dir /app cer \
 && mkdir -p /app/data && chown 10001:0 /app /app/data && chmod g+rwX /app /app/data
COPY --chown=10001:0 cer_intent/ cer_intent/
COPY --chown=10001:0 dashboard/ dashboard/
COPY --chown=10001:0 emulation/ emulation/
COPY --chown=10001:0 ns3_ceragon/ ns3_ceragon/
COPY --chown=10001:0 integrations/ integrations/
COPY --chown=10001:0 run.py .
COPY --chown=10001:0 data/ /app/data.seed/
COPY --chmod=0755 deploy/docker/entrypoint.sh /usr/local/bin/cer-entrypoint

ENV CER_INTENT_VERSION=${VERSION} \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    FLASK_DEBUG=false \
    ADAPTER_BACKEND=teraflow \
    TERAFLOW_URL=http://teraflowsdn-nbi:80 \
    TFS_REALIZATION=ietf \
    TWIN_URL=http://twin:9100 \
    CER_INTENT_MCP_MODE=advise \
    STATE_FILE=/app/data/topology_state.json \
    AUDIT_LOG_FILE=/app/data/audit_log.jsonl \
    CER_IMF_STORE=/app/data/imf_intents.json \
    CER_IMF_AUTO_STATE=/app/data/imf_auto_policy.json

LABEL org.opencontainers.image.title="CER-Intent" \
      org.opencontainers.image.description="Intent manager, slice controller and studio for Ceragon transport over TeraFlowSDN" \
      org.opencontainers.image.source="https://github.com/efidvir/cer-intent" \
      org.opencontainers.image.version="${VERSION}"

USER 10001
VOLUME ["/app/data"]
EXPOSE 5000 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('FLASK_PORT','5000'), timeout=4)"
ENTRYPOINT ["cer-entrypoint"]
CMD ["python", "run.py"]


# ── the emulated demo: radios and a TeraFlowSDN stand-in in front of the same service ─────────
# needs the fork as a named build context: --build-context fork=../teraflowsdn
FROM base AS demo
COPY --from=fork --chown=10001:0 src/common/ /opt/tfs-fork/src/common/
COPY --from=fork --chown=10001:0 src/device/__init__.py /opt/tfs-fork/src/device/__init__.py
COPY --from=fork --chown=10001:0 src/device/service/__init__.py /opt/tfs-fork/src/device/service/__init__.py
COPY --from=fork --chown=10001:0 src/device/service/driver_api/ /opt/tfs-fork/src/device/service/driver_api/
COPY --from=fork --chown=10001:0 src/device/service/drivers/ceragon/ /opt/tfs-fork/src/device/service/drivers/ceragon/
COPY --from=fork --chown=10001:0 src/service/__init__.py /opt/tfs-fork/src/service/__init__.py
COPY --from=fork --chown=10001:0 src/service/service/__init__.py /opt/tfs-fork/src/service/service/__init__.py
COPY --from=fork --chown=10001:0 src/service/service/service_handlers/ceragon_transport/ /opt/tfs-fork/src/service/service/service_handlers/ceragon_transport/
ENV TFS_FORK_SRC=/opt/tfs-fork/src \
    FLOW_TWIN_URL=http://twin:9100
EXPOSE 8088
CMD ["python", "emulation/flow_stack.py", "up", "--logs", "-"]


# ── the service (default target) ───────────────────────────────────────────────────────────
FROM base AS app
