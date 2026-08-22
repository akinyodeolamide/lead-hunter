# Lead Hunter - Production Docker Image
FROM python:3.12-slim

# Security: non-root user
RUN groupadd -r leadhunter && useradd -r -g leadhunter leadhunter

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency and source files needed for installation
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Copy test files (not needed at runtime but included for completeness)
COPY tests/ ./tests/

# Change ownership to non-root user
RUN chown -R leadhunter:leadhunter /app

# Switch to non-root user
USER leadhunter

# Expose API port
EXPOSE 8000

# Health check against API health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command: run the API server with scheduler active
CMD ["python", "-m", "uvicorn", "lead_hunter.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
