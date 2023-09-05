import streamlit as st
import asyncio
import json
import subprocess
import logging
import aiofiles
import psutil
import matplotlib.pyplot as plt
import numpy as np
import time

# Setup logging
logging.basicConfig(level=logging.INFO)

# Class for deploying and saving the application
class DeployAndSave:
    def __init__(self):
        self.version_map = {}  # To keep track of versions for each app
    
    async def deploy(self, app_name, app_repo_url, env_vars=None, resource_limits=None):
        version = self.version_map.get(app_name, "v1.0")  # Fetch the latest version or set to v1.0
        try:
            # Clone the git repo
            subprocess.run(["git", "clone", app_repo_url, app_name], check=True)
            
            # Create Dockerfile for FastAPI application
            dockerfile_content = f"""\
FROM tiangolo/uvicorn-gunicorn:python3.10-slim
COPY ./{app_name} /{app_name}
COPY ./requirements.txt /{app_name}/requirements.txt
RUN pip install --no-cache-dir -r /{app_name}/requirements.txt
"""
            with open(f"{app_name}/Dockerfile", "w") as f:
                f.write(dockerfile_content)
            
            # Build Docker image
            docker_image_name = f"{app_name}:{version}"
            subprocess.run(["docker", "build", "-t", docker_image_name, app_name], check=True)
            
            # Run Docker container
            docker_run_command = ["docker", "run", "-d", "--name", f"{app_name}_container"]
            if env_vars:
                for key, value in json.loads(env_vars).items():
                    docker_run_command.extend(["-e", f"{key}={value}"])
            if resource_limits:
                if 'cpu' in resource_limits:
                    docker_run_command.extend(['--cpus', str(resource_limits['cpu'])])
                if 'mem' in resource_limits:
                    docker_run_command.extend(['--memory', str(resource_limits['mem'])])
            docker_run_command.append(docker_image_name)
            subprocess.run(docker_run_command, check=True)
            
            # Save Docker image as a tar file
            tar_file_path = f"{app_name}_{version}.tar"
            subprocess.run(["docker", "save", "-o", tar_file_path, docker_image_name], check=True)
            
            # Increment version for the next deploy
            new_version = f"v{float(version[1:]) + 0.1}"
            self.version_map[app_name] = new_version
            
        except Exception as e:
            logging.error(f"Deployment error: {e}")

# Class for rolling back the application
class Rollback:
    async def rollback(self, app_name, version):
        try:
            tar_file_path = f"{app_name}_{version}.tar"
            subprocess.run(["docker", "load", "-i", tar_file_path], check=True)
            docker_image_name = f"{app_name}:{version}"
            subprocess.run(["docker", "run", "-d", "--name", f"{app_name}_container", docker_image_name], check=True)
        except Exception as e:
            logging.error(f"Rollback error: {e}")

# Class for monitoring and scaling the application
class MonitorAndScale:
    async def monitor_and_scale(self, app_name, log_file_path, threshold):
        instances = 1
        while True:
            try:
                request_count = await self.count_requests(log_file_path)
                logging.info(f"Request count: {request_count}")

                if request_count > threshold:
                    instances += 1
                    await self.update_caddy_config(app_name, instances)
                elif request_count < threshold and instances > 1:
                    instances -= 1
                    await self.update_caddy_config(app_name, instances)

                await asyncio.sleep(60)
            except Exception as e:
                logging.error(f"Monitoring error: {e}")

    async def count_requests(self, log_file_path):
        try:
            async with aiofiles.open(log_file_path, mode='r') as f:
                logs = await f.readlines()
            return len(logs)
        except Exception as e:
            logging.error(f"Error counting requests: {e}")
            return 0

    async def update_caddy_config(self, app_name, instances):
        caddy_config = ":80 { "
        for i in range(instances):
            caddy_config += f"reverse_proxy /{app_name}_{i}/ {{ to localhost:800{i+1} }}"
        caddy_config += " }"
        async with aiofiles.open("Caddyfile", "w") as f:
            await f.write(caddy_config)
        subprocess.run(["docker", "kill", "-s", "HUP", "caddy"], check=True)

# Initialize class instances
deploy_and_save = DeployAndSave()
rollback = Rollback()
monitor_and_scale = MonitorAndScale()

# Streamlit UI
def run_streamlit_ui():
    st.title("Mini PaaS UI")

    # Deploy new app
    st.subheader("Deploy New App")
    app_name = st.text_input("App Name")
    repo_url = st.text_input("Git Repo URL")
    deploy_button = st.button("Deploy")
    if deploy_button:
        asyncio.run(deploy_and_save.deploy(app_name, repo_url))

    # Rollback
    st.subheader("Rollback")
    rollback_app = st.text_input("App to Rollback")
    rollback_version = st.text_input("Version to Rollback To")
    rollback_button = st.button("Rollback")
    if rollback_button:
        asyncio.run(rollback.rollback(rollback_app, rollback_version))

    # Run monitor and scale
    st.subheader("Monitor and Scale")
    app_name_scale = st.text_input("App to Monitor and Scale")
    threshold = st.number_input("Threshold for Scaling", min_value=0)
    monitor_button = st.button("Monitor and Scale")
    if monitor_button:
        log_file_path = "/var/log/caddy/access.log"  # Replace this with the actual path to your Caddy log file
        asyncio.run(monitor_and_scale.monitor_and_scale(app_name_scale, log_file_path, threshold))

if __name__ == "__main__":
    run_streamlit_ui()
