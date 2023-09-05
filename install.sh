#!/bin/bash

# Update Upgrade package lists
sudo apt update -y
sudo apt upgrade -y

# Install Python and pip
sudo apt install -y python3 python3-pip

# Install Docker
sudo apt install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker

# Install Docker-Compose
sudo apt install -y docker-compose

# Create a custom Docker network
docker network create pass_network

# Install Streamlit
pip3 install streamlit

# Run common Docker containers

# Keycloak
docker run -d --name keycloak --network=my_network -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=admin -p 8080:8080 jboss/keycloak

# Redis
docker run -d --name redis --network=my_network -p 6379:6379 redis

# NATS
docker run -d --name nats --network=my_network -p 4222:4222 -p 6222:6222 -p 8222:8222 nats

# PostgreSQL
docker run -d --name postgres --network=my_network -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=admin -e POSTGRES_DB=mydatabase -p 5432:5432 postgres

# Create Caddyfile
cat > Caddyfile <<EOL
:80 {
  encode gzip
  log {
    output file /var/log/caddy/access.log {
      roll_size 1gb
      roll_keep 5
      roll_keep_for 720h
    }
    format json
  }
  reverse_proxy /* localhost:5000
}
EOL

# Caddy
docker run -d --name caddy --network=my_network -p 80:80 -p 443:443 -v $(pwd)/Caddyfile:/etc/caddy/Caddyfile caddy:2.0.0-alpine

# Download paas.py using wget
wget "https://raw.githubusercontent.com/STOCKZE/pypaas/main/paas.py"

# Run Streamlit app 
streamlit run paas.py
