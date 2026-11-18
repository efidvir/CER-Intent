# Radio emulator image for the Containerlab topology:
#   docker build -f emulation/radio-emulator.Dockerfile -t cer-intent/radio-emulator:latest emulation
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*
COPY radio_emulator.py /app/radio_emulator.py
EXPOSE 8080
CMD ["python", "/app/radio_emulator.py", "--port", "8080"]
