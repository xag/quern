# quern as a standalone MCP server over stdio: `docker run -i -v quern-data:/data quern`.
# The tree lives in /data/quern (tree.json + library/); mount a volume to keep it.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[host]"

# The CLI records each of its own runs to .quern/flight by default; a server that runs
# for as long as the client keeps it open would hold one call open the whole time.
ENV QUERN_FLIGHT=0
WORKDIR /data
ENTRYPOINT ["quern", "serve", "/data/quern"]
