FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create non-root user for security
RUN useradd -m -u 1000 jobhunter && chown -R jobhunter:jobhunter /app
USER jobhunter

# Default command (can be overridden by docker-compose or docker run)
CMD ["python", "-m", "src.cli", "worker"]
