FROM alpine:3.20

ARG GLIDER_VERSION=0.16.4
ARG GLIDER_SHA256=2b0f42d581b21545e27d5641caeb18896795620f25217f1b5d9fe2f02c685ea4

RUN apk add --no-cache curl socat tini \
    && curl -fsSL -o /tmp/glider.tar.gz \
       "https://github.com/nadoo/glider/releases/download/v${GLIDER_VERSION}/glider_${GLIDER_VERSION}_linux_amd64.tar.gz" \
    && echo "${GLIDER_SHA256}  /tmp/glider.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/glider.tar.gz -C /tmp \
    && mv /tmp/glider_${GLIDER_VERSION}_linux_amd64/glider /usr/local/bin/glider \
    && rm -rf /tmp/glider*

COPY gateway.sh /usr/local/bin/gateway.sh
RUN sed -i 's/\r$//' /usr/local/bin/gateway.sh && chmod +x /usr/local/bin/gateway.sh

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/gateway.sh"]
