# AgCloud Desktop Application

This project contains a desktop application and a notification API for an AgCloud system, utilizing Docker for containerization, a PostgreSQL database, and various services like noVNC and PyQt.

## Overview

The desktop application is built using PyQt6 and includes a GUI that interacts with a set of services running in Docker containers. The application also displays a web page (HTML) in the "Sound" tab, which is rendered in a web view.

## Requirements

Docker (for running containers)

Python 3.8+ (for running the application locally)

Docker Compose (for orchestrating multiple services)

Setup

- 1. Docker Compose Setup

To build and run the application in Docker:

Clone this repository.

Navigate to the directory containing docker-compose.yml.

Run the following command to start the application:

docker-compose up --build

- 2. Running Locally

You can also run the app.py service directly from your computer (instead of inside the container). To do this:

Ensure that all dependencies are installed:

pip install -r requirements.txt

## Run the application

python app.py

Features

GUI: Displays an interactive dashboard with embedded web views (Grafana, etc.).

Notification API: A Flask-based API interacting with a PostgreSQL database for storing schedules.

Sound Tab: Displays an HTML page in the desktop application.

noVNC: Web-based VNC client to interact with the desktop application.
