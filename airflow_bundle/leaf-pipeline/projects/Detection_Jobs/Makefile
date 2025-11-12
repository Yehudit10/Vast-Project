.PHONY: ci-e2e ci-detection

ci-e2e:
	cd e2e_kafka_flink && pytest tests --cov=e2e_pipeline --cov-report=xml --maxfail=1 -v

ci-detection:
	cd agri-baseline && pytest tests --cov=agri_baseline --cov-report=xml --maxfail=1 -v
