# Standard library only: nothing to install, the source is the app.
FROM python:3.13-slim@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962
WORKDIR /app
COPY src/ ./
USER nobody
ENV PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/health\", timeout=3)"]
CMD ["python", "-m", "creem_bridge"]
