# CER-Intent: intent API, dashboard and RFC 9543 slice controller (port 5000), MCP tools (port 8765)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ceragon_tfs_adapter/ ceragon_tfs_adapter/
RUN pip install --no-cache-dir ./ceragon_tfs_adapter

COPY cer_intent/ cer_intent/
COPY dashboard/ dashboard/
COPY data/ data/
COPY ns3_ceragon/ ns3_ceragon/
COPY integrations/ integrations/
COPY run.py .

RUN useradd --uid 10001 --create-home cer && chown -R cer /app
USER cer

ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    ADAPTER_BACKEND=teraflow \
    TERAFLOW_URL=http://teraflowsdn-nbi:80 \
    TFS_REALIZATION=ietf \
    CER_INTENT_MCP_MODE=advise

EXPOSE 5000 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/restconf/data/ietf-network-slice-service:network-slice-services', timeout=4)"

# MCP tools instead of the API:
#   docker run ... python -m cer_intent.mcp --transport streamable-http --host 0.0.0.0
CMD ["python", "run.py"]
