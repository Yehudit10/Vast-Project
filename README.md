# AgCloud

## AgCloud - Sounds

### Streaming & Simulation 2 - Kafka on KinD

This section explains how to deploy Kafka on KinD using the Bitnami Helm chart, create topics with 7-day retention, and run a smoke test with kcat.

#### Deploy Kafka on KinD using Bitnami Helm chart

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm install my-kafka bitnami/kafka -f kafka-kind/values-kafka.yaml

#### Create Topics with 7-day Retention

kubectl run topic-admin --restart=Never --rm -i --image=bitnami/kafka:latest --command -- sh -lc "bash <(kubectl get cm create-topics -o jsonpath='{.data.create-topics\.sh}')"

#### Smoke Test with kcat

"# Producer - send test message"
kubectl run kcat-producer --restart=Never --rm -i --image=edenhill/kcat:1.7.1 --command -- sh -lc "echo smoke | kcat -P -b kafka-controller-0.kafka-controller-headless.default.svc.cluster.local:9092 -t dev.robot.status"

"# Consumer - read one message from the beginning"
kubectl run kcat-consumer --restart=Never --rm -i --image=edenhill/kcat:1.7.1 -- -C -b kafka-controller-0.kafka-controller-headless.default.svc.cluster.local:9092 -t dev.robot.status -o beginning -c 1

#### Notes

- Deployed with a **single Kafka broker** (no replication).
- **Auto topic creation** is disabled via Helm values.
- Topics are created explicitly with **7-day retention** using `create-topics.sh`.
