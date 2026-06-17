FROM python:3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    ca-certificates && \
	rm -rf /var/lib/apt/lists/*

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /app

COPY ./src /app
