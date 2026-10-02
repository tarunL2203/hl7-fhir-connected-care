FROM firely-learning-base:local

USER root
RUN apk add --no-cache ca-certificates openssl

COPY rds-bundle.pem /tmp/rds-bundle.pem

RUN set -eu; \
    mkdir -p /tmp/rds-certs /usr/local/share/ca-certificates; \
    awk '/-----BEGIN CERTIFICATE-----/ {n++; f=sprintf("/tmp/rds-certs/rds-%d.crt",n)} \
         f != "" {print > f} \
         /-----END CERTIFICATE-----/ {close(f); f=""}' /tmp/rds-bundle.pem; \
    roots=0; \
    for cert in /tmp/rds-certs/*.crt; do \
        subject="$(openssl x509 -in "$cert" -noout -subject)"; \
        issuer="$(openssl x509 -in "$cert" -noout -issuer)"; \
        if [ "${subject#subject=}" = "${issuer#issuer=}" ]; then \
            cp "$cert" /usr/local/share/ca-certificates/; \
            roots=$((roots + 1)); \
        fi; \
    done; \
    test "$roots" -gt 0; \
    update-ca-certificates; \
    rm -rf /tmp/rds-certs /tmp/rds-bundle.pem

USER 1000:2000
