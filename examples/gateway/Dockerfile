# Caddy with the Cloudflare DNS module baked in (needed for DNS-01 ACME).
# The official caddy image ships no DNS plugins, so we rebuild it with xcaddy.
# Both stages are multi-arch, so this builds fine on arm64/armv7 (Raspberry Pi).
# Using another DNS provider? Swap the module: https://github.com/caddy-dns
FROM caddy:2-builder AS builder
RUN xcaddy build \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
