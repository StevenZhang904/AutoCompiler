import multiprocessing.pool
import os
import csv
import json
import uuid
import shutil
import logging
import datetime
import subprocess
import httpx
import itertools
import multiprocessing
import pandas as pd
from langchain.agents import create_react_agent
from langchain.agents import AgentExecutor,Tool
from langchain_openai import ChatOpenAI
from langchain import hub
from langchain.prompts import PromptTemplate
from tools import InteractiveDockerShell, SearchCompilationInstruction, ReadmeAI
from MultiAgentGetInstructions import GetInstructions
from MultiAgentReconcile import Reconcile
from CustomAgentExecutor import CompilationAgentExecutor
import argparse
import click
from config import *
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('chromadb').setLevel(logging.ERROR)

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

prompt = PromptTemplate.from_template(template)
question_template = model_decision_template

# def to_compile_project():
#     with open("test_projects.json","r") as fp:
#         projects = json.load(fp)
#     assert len(set([pn["name"] for pn in projects]))==len(projects), "[!] Found duplicate project name"
#     for item in projects:
#         yield (item["name"], item)

def is_elf(file):
    with open(file,"rb") as f:
        return f.read(4) == b"\x7fELF"
    
def is_archive(file):
    with open(file, "rb") as f:
        return f.read(8) in {b'!<arch>\n',b'!<thin>\n'}

def is_compiled(local_path, target_files, strict=False):
    if not target_files:
        return None
    elf_file_list = []
    for root, dirs, files in os.walk(local_path):
        for file in files:
            fp = os.path.join(root,file)
            if is_elf(fp) or is_archive(fp):
                elf_file_list.append(file)
    if strict: # only if all target files are in the file list
        for file in target_files:
            file = os.path.basename(file)
            if file not in elf_file_list:
                return False
        return True
    else: # if any target file is in the file list
        for file in target_files:
            file = os.path.basename(file)
            if file in elf_file_list:
                return True
        return False

def assemble_all_to_txt(template,tools,input,output,intermediate_steps):
    tool_names = ", ".join([tool.name for tool in tools])
    tool_info = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
    agent_scratchpad = ""
    for idx, (action, value) in enumerate(intermediate_steps):
        model_response = action.log
        tool_response = value
        agent_scratchpad += "\nThought: " + model_response if idx!=0 else model_response
        agent_scratchpad += "\nObservation: " + str(tool_response)
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

def save_logs(proj_name,question,tools,res,tools_logs,local_path,checker_ok,model_ok):
    # logging process
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S:%f")
    log_local_file = f"logs1/{proj_name}.log.{now}.txt"
    logging.info(f"[-] Saving logs to {log_local_file}")
    with open(log_local_file,"w") as file:
        s = assemble_all_to_txt(template,tools,question,res["output"],res["intermediate_steps"])
        file.write(s)
    log_local_file_json = log_local_file.replace('.txt','.json')
    logging.info(f"[-] Saving logs to {log_local_file_json}")
    with open(log_local_file_json,"w") as file:
        s = assemble_all_to_json(template,tools,question,res["output"],res["intermediate_steps"])
        json.dump({"autocompiler":s, "tools":tools_logs},file,indent='\t')

    # logging result
    run_id = res["run_id"]
    log_url = LOG_URL_TEMPLATE.format(run_id=run_id)
    process_id = os.getpid()
    with open(PROCESS_LOG_CSV_PATH+f"/{process_id}.csv","a") as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow([run_id, log_url, log_local_file, local_path, model_ok, checker_ok])

def download_project(url, local_path, download_proxy=None, timeout=120) -> bool:
    logging.info(f"[-] Downloading project from {url} to {local_path}")
    # use subprocess
    if download_proxy!=None:
        cmd = f"git clone {url} {local_path} --config http.proxy={download_proxy}"
    else:
        cmd = f"git clone {url} {local_path}"
    logging.info(f"[-] Running command: {cmd}")
    ret = subprocess.run(cmd,shell=True,capture_output=True)
    # if ret.returncode == 128:
    #     logging.info(f"[-] Project already exists in {local_path}")
    #     return True
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


def start_compile(dataset_base_path,clean_copied_project,download_proxy,strict_checker,retry,projects):
    DATASET_BASE_PATH = None
    if os.environ.get("DATASET_BASE_PATH"):
        DATASET_BASE_PATH = os.environ.get("DATASET_BASE_PATH")
    if dataset_base_path:
        DATASET_BASE_PATH = dataset_base_path
    if not DATASET_BASE_PATH:
        DATASET_BASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),"dataset")
    if not os.path.exists(DATASET_BASE_PATH):
        os.makedirs(DATASET_BASE_PATH)

    if download_proxy == None and PROXY != None:
        download_proxy=PROXY

    for info in projects:
        proj_name = info["name"]
        for _ in range(retry+1):
            url = info["url"]
            files = info.get("files",None)
            proj_path = info.get("local_path",os.path.join(DATASET_BASE_PATH,proj_name))
            if not os.path.exists(proj_path) or not os.listdir(proj_path): # if the project path is not exist or is empty
                download_project(url,proj_path,download_proxy)
            # copy new project path for compilation
            local_path = copy_project(proj_path)
            os.environ["LOCAL_PATH"] = local_path

            llm = ChatOpenAI(
                base_url=OPENAI_BASE_URL,
                api_key=OPENAI_API_KEY,
                model=OPENAI_MODEL,
                temperature=1,
                # http_client=httpx.Client(proxies=PROXY) if PROXY else None
            )
            with InteractiveDockerShell(local_path=local_path,cmd_timeout=1200) as shell:
                # define tools
                if question_template == model_decision_template:
                    get_ins = GetInstructions(project_name=proj_name)
                    rec = Reconcile()
                    tools = [
                        Tool(
                            name="SHELL",
                            description=shell.execute_command.__doc__,
                            func=shell.execute_command
                        ),
                        Tool(
                            name="GET_INSTRUCTIONS",
                            description=get_ins.get_instructions.__doc__,
                            func=get_ins.get_instructions
                        ),
                        Tool(
                            name="RECONCILE",
                            description=rec.reconcile.__doc__,
                            func=rec.reconcile
                        )
                    ]
                if question_template == rag_template:
                    search_inst_tool = SearchCompilationInstruction(directory_path=local_path, project_name=proj_name, use_proxy=PROXY)
                    tools = [
                        Tool(
                            name="SHELL",
                            description=shell.execute_command.__doc__,
                            func=shell.execute_command
                        ),
                        Tool(
                            name="SEARCH_INSTRUCTION_FROM_FILES",
                            description=search_inst_tool.search_instruction_from_files.__doc__,
                            func=search_inst_tool.search_instruction_from_files
                        ),
                        Tool(
                            name="SEARCH_URL_FROM_FILES",
                            description=search_inst_tool.search_url_from_files.__doc__,
                            func=search_inst_tool.search_url_from_files
                        ),
                        Tool(
                            name="SEARCH_INSTRUCTION_FROM_URL",
                            description=search_inst_tool.search_instruction_from_url.__doc__,
                            func=search_inst_tool.search_instruction_from_url
                        )
                    ]
                if question_template == readmeai_template:
                    readmeai_tool = ReadmeAI(url=url,project_name=proj_name)
                    tools = [
                        Tool(
                            name="SHELL",
                            description=shell.execute_command.__doc__,
                            func=shell.execute_command
                        ),
                        Tool(
                            name="READMEAI",
                            description=readmeai_tool.generate_readme_and_return_instructions.__doc__,
                            func=readmeai_tool.generate_readme_and_return_instructions
                        )
                    ]
                # define agent
                agent = create_react_agent(llm=llm,tools=tools,prompt=prompt)
                agent_executor = CompilationAgentExecutor(agent=agent,tools=tools,verbose=True,return_intermediate_steps=True,max_iterations=30,handle_parsing_errors=True)

                res = None
                question = question_template.format(project_name=proj_name)
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
                    checker_ok = is_compiled(local_path, files, strict=strict_checker)
                    checker_ok = f"{str(checker_ok)}(strict={str(strict_checker)})"
                except Exception as e:
                    print(res)
                    logging.error(f"[!] Compilation failed with error: {e}")
                    checker_ok = f"False(strict={str(strict_checker)})"
                
                if "COMPILATION-SUCCESS" in res.get("final_answer",""):
                    model_ok = "True"
                elif "COMPILATION-UNCERTAIN" in res.get("final_answer",""):
                    model_ok = "UNCERTAIN"
                else:
                    model_ok = "False"

                logging.info("[-] Project {}, model result: {}, checker result: {}, path: {}".format(proj_name,model_ok,checker_ok,local_path))

                if clean_copied_project:
                    logging.info(f"[+] Clear project compilation path {local_path}")
                    # shutil.rmtree(local_path)
                    cmd = f"echo {PASSWORD} | sudo -S rm -rf {local_path}"
                    subprocess.run(cmd,shell=True)

                if question_template == model_decision_template:
                    tools_log = {
                        "shell":shell.logger,
                        "get_instructions":get_ins.logger,
                        "reconcile":rec.logger
                    }

                if question_template == rag_template:
                    tools_log = {
                        "shell":shell.logger,
                        "search_instruction_from_files":search_inst_tool.logger1,
                        "search_url_from_files":search_inst_tool.logger2,
                        "search_instruction_from_url":search_inst_tool.logger3
                    }
                
                if question_template == readmeai_template:
                    tools_log = {
                        "shell":shell.logger,
                        "search_instruction":readmeai_tool.logger
                    }

                save_logs(proj_name,question,tools,res,tools_log,local_path,checker_ok,model_ok)

            if checker_ok.startswith("False"):
                continue
            else:
                break


@click.command()
@click.option('-j', '--json_path', type=str, required=True,
              help='the path to the project file to be compiled')
@click.option('-p', '--dataset_base_path', type=str, required=True, 
              help='the base path to store the projects need to compile')
@click.option('-c', '--clean_copied_project', type=bool, required=True, 
              help='whether to clear the new project path after the compilation, set to True when debugging')
@click.option('-r', '--retry', type=int, default=0,
              help='the times to retry when fail to pass checker')
@click.option('-s', '--strict_checker', type=bool, default=False,
              help='if True, only return True when all target files are in the file list, otherwise return True when any target file is in the file list')
@click.option('--download_proxy', type=str, 
              help='pass to git --config http.proxy=${}, e.g., socks5://127.0.0.1:29999, if do not set: do not use proxy')
@click.option('--multi_process', type=bool, default=False, 
              help='whether to enable the multi-process to compile the projects')
def main(json_path,dataset_base_path,clean_copied_project,download_proxy,strict_checker,retry,multi_process):
    '''
    Compile the projects from source code with the help of AI assistant
    '''
    with open(json_path, 'r') as fp:
        projects = json.load(fp)

    base_tuple=(dataset_base_path,clean_copied_project,download_proxy,strict_checker,retry)
    if multi_process:
        args = [base_tuple+([project],) for project in projects]
        with multiprocessing.Pool(processes=len(projects)) as pool:
            pool.starmap(start_compile, args)
    else:
        args = base_tuple+(projects,)
        start_compile(*args)

    # merge csv_data
    merge_data = []
    for filename in os.listdir(PROCESS_LOG_CSV_PATH):
        if filename.endswith(".csv") and filename[:-4].isdigit():
            file_path = os.path.join(PROCESS_LOG_CSV_PATH,filename)
            with open(file_path,"r") as fp:
                csv_reader = csv.reader(fp)
                csv_data = list(csv_reader)  
                merge_data.append(csv_data)
            # os.system(f"rm {file_path}")

    with open(LOG_CSV_PATH,"a") as fp:
        csv_writer = csv.writer(fp)
        for data in merge_data:
            for row in data:
                csv_writer.writerow(row)


if __name__ == "__main__":
    main()