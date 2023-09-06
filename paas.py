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

from matplotlib.backends.backend_agg import RendererAgg
_lock = RendererAgg.lock

# Setup logging
logging.basicConfig(level=logging.INFO)

class DeployAndSave:
    def __init__(self):
        self.version_map = {}  # To keep track of versions for each app

        # Check if a local Docker registry is already running
        result = subprocess.run(["docker", "ps", "-f", "name=local_registry"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "local_registry" not in result.stdout:
            # Initialize a local Docker registry if not already running
            subprocess.run(["docker", "run", "-d", "-p", "5000:5000", "--name", "local_registry", "registry:2"], check=True)

    async def deploy(self, app_name, app_repo_url, env_vars=None, resource_limits=None):
        version = self.version_map.get(app_name, "v1.0")  # Fetch the latest version or set to v1.0
        try:
            # Clone the git repo
            subprocess.run(["git", "clone", app_repo_url, app_name], check=True)
            
            # Create Dockerfile for FastAPI application
            dockerfile_content = f"""\
FROM tiangolo/uvicorn-gunicorn:python3.10-slim
COPY . /app
WORKDIR /app
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
"""
            with open(f"{app_name}/Dockerfile", "w") as f:
                f.write(dockerfile_content)
            
            # Build Docker image
            local_image_name = f"{app_name}:{version}"
            subprocess.run(["docker", "build", "-t", local_image_name, app_name], check=True)
            
            # Tag and push Docker image to local registry
            registry_image_name = f"localhost:5000/{local_image_name}"
            subprocess.run(["docker", "tag", local_image_name, registry_image_name], check=True)
            subprocess.run(["docker", "push", registry_image_name], check=True)
            
            # Run Docker container and map port
            host_port = 8000  # Make this dynamic based on available ports
            docker_run_command = ["docker", "run", "-d", "--name", f"{app_name}_container", "-p", f"{host_port}:80"]
            
            if env_vars:
                for key, value in json.loads(env_vars).items():
                    docker_run_command.extend(["-e", f"{key}={value}"])
            if resource_limits:
                if 'cpu' in resource_limits:
                    docker_run_command.extend(['--cpus', str(resource_limits['cpu'])])
                if 'mem' in resource_limits:
                    docker_run_command.extend(['--memory', str(resource_limits['mem'])])
            
            docker_run_command.append(registry_image_name)
            subprocess.run(docker_run_command, check=True)
            
            # Increment version for the next deploy
            new_version = f"v{float(version[1:]) + 0.1}"
            self.version_map[app_name] = new_version

            return host_port  # Return the host port for Streamlit UI
        except Exception as e:
            logging.error(f"Deployment error: {e}")
            return None

class Rollback:
    async def rollback(self, app_name, version):
        try:
            registry_image_name = f"localhost:5000/{app_name}:{version}"
            subprocess.run(["docker", "pull", registry_image_name], check=True)
            subprocess.run(["docker", "run", "-d", "--name", f"{app_name}_container", registry_image_name], check=True)
        except Exception as e:
            logging.error(f"Rollback error: {e}")


# Global variable to store the number of instances
current_instances = {}

# Class for monitoring and scaling the application
class MonitorAndScale:
    async def monitor_and_scale(self, app_name, log_file_path, threshold):
        instances = 1  # Start with one instance
        while True:
            try:
                request_count = await self.count_requests(log_file_path)
                logging.info(f"Request count: {request_count}")

                if request_count > threshold:
                    instances += 1
                elif request_count < threshold and instances > 1:
                    instances -= 1
                
                await self.update_caddy_config(app_name, instances)
                
                # Update the global variable
                current_instances[app_name] = instances

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


# Monitor and Scale class with global state update
class MonitorAndScale:
    async def monitor_and_scale(self, app_name, log_file_path, threshold):
        global current_instances  # Use the global state variable
        instances = 1  # Initial number of instances
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

                current_instances['count'] = instances  # Update the global state
                await asyncio.sleep(60)
            except Exception as e:
                logging.error(f"Monitoring error: {e}")


# Initialize class instances
deploy_and_save = DeployAndSave()
rollback = Rollback()
monitor_and_scale = MonitorAndScale()
current_instances = {'count': 1}  # Global state to store the current number of instances


def run_streamlit_ui():
    st.title("Mini PaaS UI")
      
    # Deploy new app
    st.subheader("Deploy New App")
    app_name = st.text_input("App Name")
    repo_url = st.text_input("Git Repo URL")
    threshold = st.number_input("Threshold for Auto-Scaling", min_value=0, value=10)
    deploy_button = st.button("Deploy")
    if deploy_button:
        host_port = asyncio.run(deploy_and_save.deploy(app_name, repo_url))
        if host_port:
            st.success(f"App is deployed. Access it at http://localhost:{host_port}")
            log_file_path = "/var/log/caddy/access.log"  # Replace with your actual Caddy log path
            asyncio.run(monitor_and_scale.monitor_and_scale(app_name, log_file_path, threshold))
        else:
            st.error("Failed to deploy the app.")

    rollback_button = col5.button(f"Rollback {app}")
    if rollback_button:
        st.subheader("Rollback")
        rollback_app = st.text_input("App to Rollback")
        rollback_version = st.text_input("Version to Rollback To")
        rollback_button = st.button("Rollback")
        if rollback_button:
            asyncio.run(rollback.rollback(rollback_app, rollback_version))
            
    # Show list of deployed apps
    st.subheader("List of Deployed Apps")
    deployed_apps = deploy_and_save.version_map.items()
    for app, version in deployed_apps:
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.write(f"{app}")  
        col2.write(f"{version}")  
        col3.write(f"http://localhost:{host_port}")  # Replace with the actual deployed URL and port
        redeploy_button = col4.button(f"Redeploy {app}")
        if redeploy_button:
            host_port = asyncio.run(deploy_and_save.deploy(app_name, repo_url))
            if host_port:
                st.success(f"App is deployed. Access it at http://localhost:{host_port}")
                log_file_path = "/var/log/caddy/access.log"  # Replace with your actual Caddy log path
                asyncio.run(monitor_and_scale.monitor_and_scale(app_name, log_file_path, threshold))
            else:
                st.error("Failed to deploy the app.")

    # Deploy new app in a single line
    col1, col2, col3 = st.columns(3)
    app_name = col1.text_input("App Name", key="deploy_app_name")
    repo_url = col2.text_input("Git Repo URL", key="deploy_repo_url")
    deploy_button = col3.button("Deploy", key="deploy_button")
    if deploy_button:
        host_port = asyncio.run(deploy_and_save.deploy(app_name, repo_url))
        if host_port:
            st.success(f"App is deployed. Access it at http://localhost:{host_port}")
        else:
            st.error("Failed to deploy the app.")

    # Placeholder for the live visits chart
    chart_placeholder = st.empty()
    
    # Charts - Start a loop to update the live visits chart
    while True:
        # Matplotlib chart for live visits
        st.subheader("Live Visits")
        fig, ax = plt.subplots()

        # Read log file and count visits (replace with actual log file path)
        try:
            log_file_path = "/var/log/caddy/access.log"
            with open(log_file_path, "r") as f:
                logs = f.readlines()
            request_count = len(logs)
        except Exception as e:
            request_count = 0

        # Update the chart with live data
        ax.plot([1, 2, 3], [1, 4, request_count])
        chart_placeholder.pyplot(fig)

        # Show scaling events (if any)
        for app, instances in current_instances.items():  # Assuming current_instances is updated elsewhere
            st.write(f"Current number of instances for {app}: {instances}")

        # Wait before updating again
        time.sleep(5)

if __name__ == "__main__":
    run_streamlit_ui()
