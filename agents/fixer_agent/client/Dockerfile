# The client for the fix step (M2-7). It drives the OpenHands sandbox over the private network.
# It holds the Anthropic key at run time and never a GitHub token. Built by "make build-fixer-client",
# which adds the project label. Every package is pinned in requirements.lock.
FROM python:3.13.18-slim@sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --root-user-action=ignore -r /tmp/requirements.lock && rm /tmp/requirements.lock
ENV PYTHONDONTWRITEBYTECODE=1 OPENHANDS_SUPPRESS_BANNER=1
WORKDIR /repo
