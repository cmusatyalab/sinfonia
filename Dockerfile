# SPDX-FileCopyrightText: 2022 Carnegie Mellon University
# SPDX-License-Identifier: MIT

FROM python:3-slim as base

LABEL org.opencontainers.image.description='Discovery and deployment for edge-native applications' \
      org.opencontainers.image.source='https://github.com/cmusatyalab/sinfonia' \
      org.opencontainers.image.vendor='Carnegie Mellon University' \
      org.opencontainers.image.licenses='MIT'

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base as builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.1.12 \
    POETRY_NO_INTERACTION=1

RUN pip install "poetry==$POETRY_VERSION" \
 && python -m venv /venv

COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt | /venv/bin/pip install --no-deps -r /dev/stdin

COPY src ./src
COPY tests ./tests
RUN poetry build && /venv/bin/pip install dist/*.whl

FROM base as final

ENV KUBECTL_VERSION=v1.23.2 \
    HELM_VERSION=v3.8.0

RUN apt-get update && apt-get install --no-install-recommends -y curl git \
 && apt-get clean -y && rm -rf /var/lib/apt/lists/* \
 && curl -LO "https://dl.k8s.io/release/$KUBECTL_VERSION/bin/linux/amd64/kubectl" \
 && chmod +x kubectl && mv kubectl /usr/local/bin/kubectl \
 && curl -LO "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" \
 && tar -xf "helm-${HELM_VERSION}-linux-amd64.tar.gz" linux-amd64/helm \
 && chmod +x linux-amd64/helm && mv linux-amd64/helm /usr/local/bin/helm \
 && rm -rf "helm-${HELM_VERSION}-linux-amd64.tar.gz" linux-amd64

COPY --from=builder /venv /venv

# COPY SCORES /SCORES
VOLUME ["/SCORES"]
ENV SINFONIA_SCORES=/SCORES

EXPOSE 5000

ENTRYPOINT ["/venv/bin/sinfonia-tier2"]
CMD ["serve"]
