import streamlit as st
import asyncio
import subprocess
import logging
import socket
import json

# Function to check if a port is in use
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

logging.basicConfig(level=logging.INFO)

class DeployAndSave:
    def __init__(self):
        try:
            with open('state.json', 'r') as f:
                state = json.load(f)
                self.version_map = state.get('version_map', {})
                self.repo_map = state.get('repo_map', {})
                self.port_map = state.get('port_map', {})
        except:
            self.version_map = {}
            self.repo_map = {}
            self.port_map = {}
        
        self.next_port = max(self.port_map.values(), default=8000) + 1

    def save_state(self):
        state = {
            'version_map': self.version_map,
            'repo_map': self.repo_map,
            'port_map': self.port_map,
        }
        with open('state.json', 'w') as f:
            json.dump(state, f)

    async def deploy(self, app_name, app_repo_url):
        version = self.version_map.get(app_name, 'v1.0')
        try:
            subprocess.run(['git', 'clone', app_repo_url, app_name], check=True)
            self.repo_map[app_name] = app_repo_url
            dockerfile_content = """FROM tiangolo/uvicorn-gunicorn:python3.10-slim
COPY . /app
WORKDIR /app
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
"""
            with open(f"{app_name}/Dockerfile", 'w') as f:
                f.write(dockerfile_content)
            local_image_name = f"{app_name}:{version}"
            subprocess.run(['docker', 'build', '-t', local_image_name, app_name], check=True)
            registry_image_name = f"localhost:5000/{local_image_name}"
            subprocess.run(['docker', 'tag', local_image_name, registry_image_name], check=True)
            subprocess.run(['docker', 'push', registry_image_name], check=True)

            while is_port_in_use(self.next_port):
                self.next_port += 1

            host_port = self.next_port
            self.next_port += 1
            self.port_map[app_name] = host_port

            subprocess.run(['docker', 'run', '-d', '--name', f"{app_name}_container", '-p', f"{host_port}:80", registry_image_name], check=True)
            new_version = f"v{float(version[1:]) + 0.1}"
            self.version_map[app_name] = new_version

            self.save_state()
            
            return host_port
        except Exception as e:
            logging.error(f"Deployment error: {e}")
            return None

deploy_and_save = DeployAndSave()

def get_ip_address():
    return socket.gethostbyname(socket.gethostname())

def run_streamlit_ui():
    st.title('Mini PaaS UI')
    ip_address = get_ip_address()

    col1, col2 = st.columns([4, 1])
    repo_url = col1.text_input('Git Repo URL')
    deploy_button = col2.button('Deploy')

    if deploy_button:
        host_port = asyncio.run(deploy_and_save.deploy(repo_url.split('/')[-1], repo_url))
        if host_port:
            st.success(f"App is deployed. Access it at http://{ip_address}:{host_port}")
        else:
            st.error('Failed to deploy the app.')

    st.subheader('List of Deployed Apps')

    if deploy_and_save.version_map:
        for app, version in deploy_and_save.version_map.items():
            col1, col2, col3, col4 = st.columns([3, 3, 1, 1])
            col1.write(app)
            col2.write(f"http://{ip_address}:{deploy_and_save.port_map.get(app, 8000)}")
            col3.write(version)

            versions = list(deploy_and_save.version_map.values())
            selected_version = col4.selectbox("Version", versions, index=versions.index(version))

    else:
        st.write("No apps have been deployed.")

if __name__ == '__main__':
    run_streamlit_ui()
