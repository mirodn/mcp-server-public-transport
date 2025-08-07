# Dockerfile for MCP Server
FROM python:3.11-slim
WORKDIR /app

# Install build tools
COPY pyproject.toml setup.py* /app/
RUN pip install --no-cache-dir wheel setuptools

# Install your package
RUN pip install --no-cache-dir .

# Copy code
COPY . /app

# Expose HTTP-Stream port
EXPOSE 8080

# Start in HTTP-Stream mode at /mcp/
CMD ["python", "server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8080", "--path", "/mcp/"]

