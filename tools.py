import os
import time
import json
import httplib2
import paramiko
import subprocess
from tqdm import tqdm
from typing import List
from langchain.tools import tool
from googleapiclient.discovery import build
from langchain_community.utilities import GoogleSerperAPIWrapper
from ipdb import set_trace as bp


@tool
def google_search(query, topk=8, **kwargs):
    """
    Google Search is used to search for recent information and questions that you are completely unaware of.
    @param query: The search query.
    @param topk: The number of results to return.
    """
    #API_KEY = "a876031fdfbb1f28c3f1e6b2b9ba3a0bf9ec708ea13334aaa83a452acf0580fe"
    API_KEY = "AIzaSyC4Yd6p1DHuOmy-t2MPAgakIo7DtDmexqI"
    SEARCH_ENGINE_ID = "54b9e967650604352"

    proxy_info = httplib2.ProxyInfo(proxy_type=httplib2.socks.PROXY_TYPE_SOCKS5, proxy_host="127.0.0.1", proxy_port=29999)
    http = httplib2.Http(proxy_info=proxy_info)

    service = build("customsearch", "v1", developerKey=API_KEY, http=http)
    res = service.cse().list(q=query, cx=SEARCH_ENGINE_ID, num=topk, **kwargs).execute()
    search_result = res.get("items",[])
    search_result_links = [item["link"] for item in search_result]
    if isinstance(search_result_links,list):
        message = json.dumps(
            [link.encode("utf-8","ignore").decode("utf-8") for link in search_result_links]
        )
    else:
        message = search_result_links.encode("utf-8","ignore").decode("utf-8")
    # raise Exception("[!]TODO unimplemented, we need judge which results is the most possible solution for the question(query).")
    return message

@tool
def doc_sum(file_path:str)->str:
    '''
    A tool for summarizing the documentation of a project, and find out the compilation instruction.
    @param file_path: The absolute path of the documentation file, e.g. /work/README.md
    '''
    if ", " in file_path:
        return "the input doc_path should be a single file path"
    if not os.path.isabs(file_path):
        return "The documentation file path should be absolute."
    local_path = os.environ["LOCAL_PATH"]
    file_path = file_path.replace("/work", local_path)
    if not os.path.exists(file_path):
        return "The documentation file does not exist."
    print("[!] read doc file succ:", file_path)
    return """I've successfully used the code on 64bit x86, 32bit ARM and 8 bit AVR platforms.

GCC size output when only CTR mode is compiled for ARM:

$ arm-none-eabi-gcc -Os -DCBC=0 -DECB=0 -DCTR=1 -c aes.c
$ size aes.o
   text    data     bss     dec     hex filename
   1171       0       0    1171     493 aes.o
.. and when compiling for the THUMB instruction set, we end up well below 1K in code size.

$ arm-none-eabi-gcc -Os -mthumb -DCBC=0 -DECB=0 -DCTR=1 -c aes.c
$ size aes.o
   text    data     bss     dec     hex filename
    903       0       0     903     387 aes.o
I am using the Free Software Foundation, ARM GCC compiler:

$ arm-none-eabi-gcc --version
arm-none-eabi-gcc (4.8.4-1+11-1) 4.8.4 20141219 (release)
Copyright (C) 2013 Free Software Foundation, Inc.
This is free software; see the source for copying conditions.  There is NO
warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE."""

@tool
def makefile_reader(file_path:str)->str:
    """
    This is a tool to find out all the compilation targets defined in the makefile, i.e. the binaries that should be compiled out.
    @param file_path: The absolute path of the makefile, e.g. /work/Makefile
    """
    if ", " in file_path:
        return "the input doc_path should be a single file path"
    return json.dumps([
        "aes.o",
    ])

class InteractiveDockerShell:
    HOSTNAME = 'c0mpi1er-c0nta1ner'
    def __init__(self, local_path, image_name='autocompiler:gcc13', timeout=30):
        try:
            container_id = subprocess.run(f"docker run --hostname {self.HOSTNAME} -v {local_path}:/work/ -itd {image_name} /bin/bash", 
                                          shell=True, capture_output=True).stdout.decode().strip()
            assert len(container_id)==64, "Failed to create the container."
            json_str = subprocess.run(f"docker inspect {container_id}", shell=True, capture_output=True).stdout.decode()
            ipaddr = json.loads(json_str)[0]['NetworkSettings']['IPAddress']
            retcode = subprocess.run(f"docker exec {container_id} /bin/bash -c 'service ssh start'", shell=True, capture_output=True).returncode
            assert retcode==0, "Failed to start the ssh service."
        except Exception as e:
            raise Exception(f"Failed to create the container, error: {str(e)}")

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(ipaddr, username='root', password='root', port=22)
        self.session = self.client.invoke_shell()
        time.sleep(1)
        self.session.recv(1024) # skip the welcome message
        self.timeout = timeout
        self.container_id = container_id
        self.last_line = "root@c0mpi1er-c0nta1ner:/work# "
        self.logger = []

    def execute_command(self, command:str) -> str:
        """
        Execute a command in a interactive shell on the local machine (on Ubuntu 22.04 with root user). Initially, we are in the /work/ directory.
        @param cmd: The command to execute.
        """
        if self.session is None:
            raise Exception("No session available.")

        # clean the command
        command = command.strip()
        if command.startswith("`") and command.endswith("`"):
            command = command[1:-1]

        if "git " in command and "proxychains git " not in command:
            command = command.replace("git ", "proxychains git ")
        if "curl " in command and "proxychains curl " not in command:
            command = command.replace("curl ", "proxychains curl ")
        if "wget " in command and "proxychains wget " not in command:
            command = command.replace("wget ", "proxychains wget ")
        if "apt install " in command:
            command = command.replace("apt install ", "apt install -y ")
        if "apt-get install " in command:
            command = command.replace("apt-get install ", "apt-get install -y ")

        if "make install" in command:
            return "Tips: Do not install the project, just compile it!"

        self.session.send(command + '\n')

        start_time = time.time()
        output = ""
        while True:
            if time.time() - start_time > self.timeout: # execution timeout
                self.session.send('\x03')
                while self.HOSTNAME not in output:
                    if time.time() - start_time > self.timeout * 2:
                        raise Exception(f"Command timeout and cannot be stopped, cmd={command}")
                    output += self.session.recv(1024).decode('utf-8')
                output += "\nCommand execution timeout!"
                return self.omit(command, output)
            
            if self.HOSTNAME in output: # return condition
                return self.omit(command, output)
            # read outputs
            if self.session.recv_ready():
                while self.session.recv_ready():
                    output += self.session.recv(1024).decode('utf-8')
                time.sleep(0.5)  # add a delay after receiving output
            else:
                time.sleep(0.5)
        

    def omit(self, command, output)->str:
        '''
        omit the command from the output for special commands
        '''
        output = self.last_line + output
        self.logger.append((command,output)) # log the command and output in raw
        # get last line of the output
        self.last_line = output.split("\n")[-1]
        # omit output
        if command.startswith("make"):
            return "\n".join(output.split("\n")[-30:])
        elif command.startswith("configure"):
            return "\n".join(output.split("\n")[-20:])
        elif command.startswith("cmake"):
            return "\n".join(output.split("\n")[-20:])
        else:
            if len(output)>3000:
                output = output[:3000]
            return output

    def close(self):
        print("[!] stopping docker container, please wait a second...")
        if self.client:
            self.client.close()
        if self.container_id:
            subprocess.run(f"docker stop {self.container_id}", shell=True)
            subprocess.run(f"docker rm {self.container_id}", shell=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    # DEMO
    with InteractiveDockerShell(local_path="/data/huli/CompileAgent/dataset/tiny-AES-c") as shell:
        print("="*60)
        print(shell.execute_command('tree /work/ -L 2'))
        print("="*60)
        print(shell.execute_command('sleep 3 ; echo "hello"'))
        print("="*60)
        print(shell.execute_command('ls'))
        print("="*60)
        print(shell.execute_command('gcc -v'))
        print("="*60)
        print(shell.execute_command('uname -a'))
        print("="*60)


