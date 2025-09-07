# syntax=docker/dockerfile:1.6
ARG PROM_VERSION=2.54.1

FROM alpine:3.20 AS downloader
ARG PROM_VERSION
RUN apk add --no-cache ca-certificates curl tar
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN update-ca-certificates

WORKDIR /tmp
RUN curl -fsSL -o prom.tar.gz \
  https://github.com/prometheus/prometheus/releases/download/v${PROM_VERSION}/prometheus-${PROM_VERSION}.linux-amd64.tar.gz \
  && tar -xzf prom.tar.gz

FROM alpine:3.20
ARG PROM_VERSION
RUN addgroup -S prom && adduser -S -G prom prom
RUN apk add --no-cache ca-certificates tzdata
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN update-ca-certificates

COPY --from=downloader /tmp/prometheus-${PROM_VERSION}.linux-amd64/prometheus /bin/prometheus
COPY --from=downloader /tmp/prometheus-${PROM_VERSION}.linux-amd64/promtool   /bin/promtool
COPY --from=downloader /tmp/prometheus-${PROM_VERSION}.linux-amd64/console_libraries /etc/prometheus/console_libraries
COPY --from=downloader /tmp/prometheus-${PROM_VERSION}.linux-amd64/consoles  /etc/prometheus/consoles

COPY prometheus.yml /etc/prometheus/prometheus.yml

RUN mkdir -p /prometheus && chown -R prom:prom /etc/prometheus /prometheus
USER prom
EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost:9090/-/ready >/dev/null 2>&1 || exit 1

CMD ["/bin/prometheus", \
 "--config.file=/etc/prometheus/prometheus.yml", \
 "--storage.tsdb.path=/prometheus", \
 "--web.console.libraries=/etc/prometheus/console_libraries", \
 "--web.console.templates=/etc/prometheus/consoles", \
 "--web.enable-lifecycle", \
 "--storage.tsdb.retention.time=15d"]
