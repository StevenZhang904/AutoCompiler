import os
from langchain.agents import create_react_agent
from langchain.agents import AgentExecutor,Tool
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatZhipuAI
from langchain import hub
from langchain.prompts import PromptTemplate
from tools import InteractiveDockerShell, doc_sum, makefile_reader
from langchain_community.utilities import GoogleSerperAPIWrapper
import datetime
import csv
from config import *

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
6. Use the MAKEFILE_READER tool to find out all the compilation targets defined in the makefile after the compilation, and use `find` in SHELL to check out if files exist.
7. After checking, you need to output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""
# You can read the README.md file in the project path to find compilation guide. 
# If any problems occur during compilation, please use Google search tools to solve them first.

def to_compile_project():
    projects = {
        "tiny-AES-c": {
            "local_path": "/data/huli/CompileAgent/dataset/tiny-AES-c",
            "url": "https://github.com/kokke/tiny-AES-c",
            "files": [
                "aes.o",
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
    
def assemble_all(template,tools,input,output,intermediate_steps):
    tool_names = ", ".join([tool.name for tool in tools])
    tool_info = "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
    agent_scratchpad = ""
    for idx, (action, value) in enumerate(intermediate_steps):
        model_response = action.log
        tool_response = value
        agent_scratchpad += "\nThought: " + model_response if idx!=0 else model_response
        agent_scratchpad += "\nObservation: " + tool_response
    agent_scratchpad += "\nThought: " + output
    with open("agent_scratchpad.txt","w") as file:
        file.write(agent_scratchpad)
    result = template.format(tools=tool_info,tool_names=tool_names,input=input,agent_scratchpad=agent_scratchpad)
    return result

def save_logs(question,res,ok):
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S:%f")
    log_local_file = f"logs/log.{now}.txt"
    with open(log_local_file,"w") as file:
        s = assemble_all(template,tools,question,res["output"],res["intermediate_steps"])
        file.write(s)
    model_ok = "COMPILATION-SUCCESS" in res['output']
    run_id = res["run_id"]
    log_url = LOG_URL_TEMPLATE.format(run_id=run_id)
    with open("logs/statistics.csv","a") as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow([run_id, log_url, log_local_file, model_ok, ok])

if __name__ == "__main__":
    for proj_name,info in to_compile_project():
        url = info["url"]
        files = info["files"]
        local_path = info["local_path"]
        os.environ["LOCAL_PATH"] = local_path
        question = question_template.format(url=url)

        # define tools
        with InteractiveDockerShell(local_path=local_path,timeout=120) as shell:
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
            agent_executor = AgentExecutor(agent=agent,tools=tools,verbose=True,return_intermediate_steps=True,max_iterations=30,handle_parsing_errors=True)

            res = None
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
                    #print(step)
            # print("=========================================")
            # print(res["intermediate_steps"])
            # print(type(res["intermediate_steps"]))
            ok = is_compiled(local_path, files)
            save_logs(question,res,ok)
