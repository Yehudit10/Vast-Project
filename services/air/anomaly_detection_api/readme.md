docker build -t anomaly-api .

docker run -d -p 8010:8000 anomaly-api

docker compose up -d

http://localhost:8010/docs
