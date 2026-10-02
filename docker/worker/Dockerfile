# AI Work Supervisor - Sandboxed Worker Container Image
FROM python:3.11-slim

# Create dedicated non-root execution user and group
RUN groupadd -r worker && useradd -r -g worker -m -d /home/worker worker

# Install minimal system tools (git, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install pinned Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Ensure workspace directory permissions
RUN chown -R worker:worker /workspace

# Switch to unprivileged non-root user
USER worker

# Default health check command
CMD ["python", "--version"]
