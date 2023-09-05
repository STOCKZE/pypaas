#!/bin/bash
#set -e

# Update and Upgrade package lists
sudo apt update -y
sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y -o Dpkg::Options::="--force-confnew"

# Install Python and pip
sudo apt install -y python3 python3-pip

# Install Docker
sudo apt install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker

# Install Docker-Compose
sudo apt install -y docker-compose

# Create a custom Docker network
sudo docker network create pass_network

# Install Streamlit & other paas.py dependencies
sudo pip3 install streamlit asyncio aiofiles psutil matplotlib numpy

# Run common Docker containers with auto-restart

# Keycloak
#sudo docker run -d --restart=always --name keycloak --network=pass_network -e KEYCLOAK_USER=admin -e KEYCLOAK_PASSWORD=admin -p 8080:8080 jboss/keycloak

# Redis
#sudo docker run -d --restart=always --name redis --network=pass_network -p 6379:6379 redis

# NATS
#sudo docker run -d --restart=always --name nats --network=pass_network -p 4222:4222 -p 6222:6222 -p 8222:8222 nats

# PostgreSQL
#sudo docker run -d --restart=always --name postgres --network=pass_network -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=admin -e POSTGRES_DB=mydatabase -p 5432:5432 postgres

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
sudo docker run -d --name caddy --network=pass_network -p 80:80 -p 443:443 -v $(pwd)/Caddyfile:/etc/caddy/Caddyfile caddy:2.0.0-alpine

# Download paas.py using wget
wget "https://raw.githubusercontent.com/STOCKZE/pypaas/main/paas.py"

# Create and enable a systemd service for the Streamlit app
sudo bash -c 'cat > /etc/systemd/system/streamlit-app.service <<EOL
[Unit]
Description=Streamlit App Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 -m streamlit run /path/to/your/paas.py
Restart=always
User=$(whoami)

[Install]
WantedBy=multi-user.target
EOL'

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable and start the Streamlit systemd service
sudo systemctl enable streamlit-app.service
sudo systemctl start streamlit-app.service
