# Debian base on purpose: musl's resolver (alpine) races all nameservers and
# loses tailnet/VPN names to a faster NXDOMAIN; glibc resolves them reliably.
FROM python:3-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY bifrost-caddy-sync.sh /usr/local/bin/bifrost-caddy-sync
RUN chmod +x /usr/local/bin/bifrost-caddy-sync
ENTRYPOINT ["/usr/local/bin/bifrost-caddy-sync"]
CMD ["--loop"]
