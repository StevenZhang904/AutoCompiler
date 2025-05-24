import subprocess
import logging
import uuid
import os

def download_project(url, local_path, download_proxy=None, timeout=120) -> bool:
    logging.info(f"[-] Downloading project from {url} to {local_path}")
    # use subprocess
    if download_proxy!=None:
        cmd = f"git clone {url} {local_path} --config http.proxy={download_proxy}"
    else:
        cmd = f"git clone {url} {local_path}"
    logging.info(f"[-] Running command: {cmd}")
    ret = subprocess.run(cmd,shell=True,capture_output=True)
    if ret.returncode != 0:
        raise Exception(f"Failed to download project from {url}\n\n{ret.stderr.decode()}")
    return True

def copy_project(local_path):
    UUID = uuid.uuid4()
    local_path = os.path.abspath(local_path)
    new_path = f"{local_path}-{UUID}"
    cmd = f"chmod -R 777 {local_path} && cp -r {local_path} {new_path} && chmod -R 777 {new_path}"
    logging.info(f"[-] Copy project from {local_path} to {new_path}")
    ret = subprocess.run(cmd,shell=True,capture_output=True)
    if ret.returncode != 0:
        raise Exception(f"Failed to copy project from {local_path} to {new_path} {ret.stderr}")
    return new_path