import os
import csv
import json
import fire
import uuid
import shutil
import logging
import datetime
import subprocess

from langchain.agents import create_react_agent
from langchain.agents import AgentExecutor,Tool
from langchain_openai import ChatOpenAI
from langchain import hub
from langchain.prompts import PromptTemplate
from tools import InteractiveDockerShell, doc_sum, makefile_reader
from config import *
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
logging.getLogger('httpx').setLevel(logging.ERROR)

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

llm = ChatOpenAI(
    base_url="https://api.fireworks.ai/inference/v1",
    api_key=OPENAI_API_KEY,
    model="accounts/fireworks/models/mixtral-8x7b-instruct",
    temperature=0,
)

prompt = PromptTemplate.from_template(template)

question_template = """You are an experienced software development engineer. I want you help me compile a project from source code
Please complete the compilation task step by step, use the tools provided if require (one tool each time).

The project has been downloaded into /work/, which is also the SHELL's initial path.
The following information could be helpful:
1. Use `tree <dir> -L <depth>` in SHELL to check the directory structure.
2. Find out the compilation guide using DOC_SUM tool to summarize the files that you consider them as documentations.
3. Use `cat` in SHELL to check the content of any file from the project.
4. Do not install the project, just compile it.
5. Make sure that compile the project in the right path.
6. Use the MAKEFILE_READER tool to find out all the compilation targets defined in the makefile after the compilation.
7. To verify the compilation result, you need to check whether the target files exist, using `find` in SHELL, and you need to output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""
# You can read the README.md file in the project path to find compilation guide. 
# If any problems occur during compilation, please use Google search tools to solve them first. 

def to_compile_project():
    projects = {
        "tiny-AES-c": {
            "local_path": "/data/huli/CompileAgent/dataset/tiny-AES-c",
            "url": "https://github.com/kokke/tiny-AES-c",
            "files": [
                "test.elf",
            ],
        },
    }
    # with open("projects.json","r") as file:
    #     projects = json.load(file)
    for proj_name,info in projects.items():
        yield (proj_name, info)

def is_compiled(local_path, files):
    if not files:
        return None
    for file in files:
        file_path = os.path.join(local_path,file)
        if not os.path.exists(file_path):
            return False
    return True
    
def assemble_all_to_txt(template,tools,input,output,intermediate_steps):
    tool_names = ", ".join([tool.name for tool in tools])
    tool_info = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
    agent_scratchpad = ""
    for idx, (action, value) in enumerate(intermediate_steps):
        model_response = action.log
        tool_response = value
        agent_scratchpad += "\nThought: " + model_response if idx!=0 else model_response
        agent_scratchpad += "\nObservation: " + tool_response
    agent_scratchpad += "\nThought: " + output
    result = template.format(tools=tool_info,tool_names=tool_names,input=input,agent_scratchpad=agent_scratchpad)
    return result

def assemble_all_to_json(template,tools,input,output,intermediate_steps):
    tool_names = ", ".join([tool.name for tool in tools])
    tool_info = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
    init_question = template.format(tools=tool_info,tool_names=tool_names,input=input,agent_scratchpad="")
    _pair = [init_question]
    log_list = []
    for idx, (action, value) in enumerate(intermediate_steps):
        model_response = action.log
        _pair.append(model_response)
        log_list.append(_pair)
        tool_response = value
        _pair = [tool_response]
    final_output = output
    _pair.append(final_output)
    log_list.append(_pair)
    return log_list

def save_logs(question,tools,res,local_path,ok):
    # logging process
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S:%f")
    log_local_file = f"logs/log.{now}.txt"
    with open(log_local_file,"w") as file:
        s = assemble_all_to_txt(template,tools,question,res["output"],res["intermediate_steps"])
        file.write(s)
    with open(log_local_file.replace(".txt",".json"),"w") as file:
        s = assemble_all_to_json(template,tools,question,res["output"],res["intermediate_steps"])
        json.dump(s,file,indent='\t')
    # logging result
    model_ok = "COMPILATION-SUCCESS" in res['final_answer']
    run_id = res["run_id"]
    log_url = LOG_URL_TEMPLATE.format(run_id=run_id)
    with open("logs/statistics.csv","a") as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow([run_id, log_url, log_local_file, local_path, model_ok, ok])

def download_project(url, local_path, download_proxy=None, timeout=120) -> bool:
    logging.info(f"[-] Downloading project from {url} to {local_path}")
    # use subprocess
    if download_proxy!=None:
        cmd = f"git clone {url} {local_path} --config http.proxy={download_proxy}"
    else:
        cmd = f"git clone {url} {local_path}"
    logging.info(f"[-] Running command: {cmd}")
    ret = subprocess.run(cmd,shell=True,capture_output=True,timeout=timeout)
    if ret.returncode == 128:
        logging.info(f"[-] Project already exists in {local_path}")
        return True
    if ret.returncode != 0:
        raise Exception(f"Failed to download project from {url}\n\n{ret.stderr.decode()}")
    return True

def copy_project(local_path):
    UUID = uuid.uuid4()
    local_path = os.path.abspath(local_path)
    new_path = f"{local_path}-{UUID}"
    cmd = f"cp -r {local_path} {new_path}"
    logging.info(f"[-] Copy project from {local_path} to {new_path}")
    ret = subprocess.run(cmd,shell=True,capture_output=True)
    if ret.returncode != 0:
        raise Exception(f"Failed to copy project from {local_path} to {new_path}")
    return new_path

def main(
        dataset_base_path:str = None,
        clear_new_project:bool = False,
        download_proxy:str = None,
        ):
    '''
    Compile the projects from source code with the help of AI assistant
    
    Args:
        dataset_base_path (str): the base path to store the projects need to compile
        clear_new_project (bool): whether to clear the new project path after the compilation, set to True when debugging
        download_proxy (str): pass to git --config http.proxy=${}, e.g., socks5://127.0.0.1:9999, if do not set: do not use proxy
    '''
    DATASET_BASE_PATH = None
    if os.environ.get("DATASET_BASE_PATH"):
        DATASET_BASE_PATH = os.environ.get("DATASET_BASE_PATH")
    if dataset_base_path:
        DATASET_BASE_PATH = dataset_base_path
    if not DATASET_BASE_PATH:
        DATASET_BASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),"dataset")
    if not os.path.exists(DATASET_BASE_PATH):
        os.makedirs(DATASET_BASE_PATH)

    for proj_name,info in to_compile_project():
        url = info["url"]
        files = info.get("files",None)
        proj_path = info.get("local_path",os.path.join(DATASET_BASE_PATH,proj_name))
        if not os.path.exists(proj_path) or not os.listdir(proj_path): # if the project path is not exist or is empty
            download_project(url,proj_path,download_proxy)
        # copy new project path for compilation
        local_path = copy_project(proj_path)
        os.environ["LOCAL_PATH"] = local_path

        with InteractiveDockerShell(local_path=local_path,timeout=120) as shell:
            # define tools
            tools = [
                Tool(
                    name="SHELL",
                    description=shell.execute_command.__doc__,
                    func=shell.execute_command
                ),
                Tool(
                    name="DOC_SUM",
                    description=doc_sum.__doc__,
                    func=doc_sum
                ),
                Tool(
                    name="MAKEFILE_READER",
                    description=makefile_reader.__doc__,
                    func=makefile_reader
                ),
            ]
            # define agent
            agent = create_react_agent(llm=llm,tools=tools,prompt=prompt)
            agent_executor = AgentExecutor(agent=agent,tools=tools,verbose=True,return_intermediate_steps=True,max_iterations=2,handle_parsing_errors=True)

            res = None
            question = question_template.format(url=url)
            try:
                for step in agent_executor.iter({"input":question},include_run_info=True):
                    if "intermediate_step" in step:
                        pass
                    else:
                        res = {
                            "final_answer" : step["output"],
                            "intermediate_steps" : step["intermediate_steps"],
                            "output" : step["messages"][0].content,
                            "run_id" : str(step["__run"].run_id)
                        }
                        if not res["output"]:
                            res["output"] = res["final_answer"]
                        # print(step)
                ok = is_compiled(local_path, files)
            except Exception as e:
                logging.error(f"[!] Compilation failed with error: {e}")
                ok = False
            save_logs(question,tools,res,local_path,ok)
        
        if clear_new_project:
            logging.info(f"[-] Clear project compilation path {local_path}")
            shutil.rmtree(local_path)

if __name__ == "__main__":
    fire.Fire(main)