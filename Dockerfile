FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -U pip setuptools wheel \
 && pip install --no-cache-dir .

# The port is read from $PORT (set by Cloud Run & co.), defaulting to 8080
ENV PORT=8080 \
    MCP_STATELESS=true
EXPOSE 8080

CMD ["python", "server.py", "--transport", "http", "--host", "0.0.0.0", "--path", "/mcp"]
