# Dockerfile — KinD + Helm + Kafka (clean)
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Base OS packages and common tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates bash curl iproute2 iptables socat jq tar docker.io openssl sed procps \
 && rm -rf /var/lib/apt/lists/*

# Tool versions
ENV KUBECTL_VERSION=1.30.2 \
    KIND_VERSION=0.23.0 \
    HELM_VERSION=3.15.2

# kubectl
RUN curl -fsSL \
     -o /usr/local/bin/kubectl \
     "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
 && chmod +x /usr/local/bin/kubectl

# kind
RUN curl -fsSL \
     -o /usr/local/bin/kind \
     "https://kind.sigs.k8s.io/dl/v${KIND_VERSION}/kind-linux-amd64" \
 && chmod +x /usr/local/bin/kind

# helm
RUN curl -fsSL "https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz" \
 | tar -xz -C /tmp \
 && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
 && chmod +x /usr/local/bin/helm \
 && rm -rf /tmp/linux-amd64

# -------- entrypoint --------
RUN cat > /usr/local/bin/entrypoint.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

retry() { # retry <times> <sleep> <cmd...>
  local -r times="$1"; shift
  local -r pause="$1"; shift
  local n=1
  until "$@"; do
    if (( n >= times )); then return 1; fi
    echo "retry $n/$times failed; retrying in ${pause}s..." >&2
    sleep "$pause"; ((n++))
  done
}

VALUES_FILE=${VALUES_FILE:-/work/values-kafka.yaml}
TOPICS_SCRIPT=${TOPICS_SCRIPT:-/work/create-topics.sh}
CLUSTER_NAME=${CLUSTER_NAME:-kafka-kind}
NAMESPACE=${NAMESPACE:-default}
RETENTION_DAYS=${RETENTION_DAYS:-7}

if [[ ! -f "$VALUES_FILE" ]]; then
  echo "Missing values file: $VALUES_FILE (mount it: -v \$(pwd)/values-kafka.yaml:/work/values-kafka.yaml:ro)" >&2
  exit 1
fi
if [[ ! -f "$TOPICS_SCRIPT" ]]; then
  echo "Missing topics script: $TOPICS_SCRIPT (mount it: -v \$(pwd)/create-topics.sh:/work/create-topics.sh:ro)" >&2
  exit 1
fi

echo "==> Creating KinD cluster: $CLUSTER_NAME"
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "Cluster $CLUSTER_NAME already exists, deleting..."
  kind delete cluster --name "$CLUSTER_NAME" || true
fi
retry 3 5 kind create cluster --name "$CLUSTER_NAME" --wait 120s

# Patch kubeconfig so it's reachable from inside the container (not 127.0.0.1)
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
CP_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${CLUSTER_NAME}-control-plane" 2>/dev/null || true)"
if [[ -n "$CP_IP" ]]; then
  echo "Patching kubeconfig at $KUBECONFIG_PATH to server https://$CP_IP:6443"
  sed -i -E "s#server: https://127\.0\.0\.1:[0-9]+#server: https://$CP_IP:6443#g" "$KUBECONFIG_PATH"
fi

echo "==> Checking Kubernetes API reachability"
retry 10 3 kubectl --request-timeout=5s cluster-info >/dev/null

echo "==> Helm install Bitnami Kafka (values: $VALUES_FILE)"
retry 3 3 helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null
retry 3 3 helm repo update >/dev/null
retry 3 10 helm upgrade --install kafka bitnami/kafka \
  -n "$NAMESPACE" -f "$VALUES_FILE" --create-namespace

echo "==> Waiting for Kafka pods to be Ready (up to 10m)"
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app.kubernetes.io/name=kafka --timeout=600s

POD="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=kafka -o jsonpath="{.items[0].metadata.name}")"
echo "Kafka pod: $POD"

echo "==> Copy & run topics script inside the pod (normalize CRLF if needed)"
kubectl -n "$NAMESPACE" exec -i "$POD" -- bash -lc \
  "cat > /tmp/create-topics.sh && sed -i 's/\r$//' /tmp/create-topics.sh && chmod +x /tmp/create-topics.sh" < "$TOPICS_SCRIPT"

kubectl -n "$NAMESPACE" exec "$POD" -- bash -lc \
  "RETENTION_DAYS=$RETENTION_DAYS BOOTSTRAP=localhost:9092 /tmp/create-topics.sh"

echo "==> Start port-forward service/kafka 29092 -> 9092 (0.0.0.0)"
(
  while true; do
    kubectl -n "$NAMESPACE" port-forward --address=0.0.0.0 svc/kafka 29092:9092 || true
    echo "port-forward dropped; restarting in 1s..."
    sleep 1
  done
) &

echo "Kafka reachable at: localhost:29092"
tail -f /dev/null
EOF

RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
