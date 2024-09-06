import os
import time
import json
import logging
import httplib2
import paramiko
import subprocess
import requests
import chardet
import httpx
import openai
from tqdm import tqdm
from typing import List
from langchain.tools import tool
from googleapiclient.discovery import build
from langchain_chroma import Chroma
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.runnables import RunnableLambda
from langchain.schema.runnable import RunnablePassthrough
from langchain.prompts import PromptTemplate
from langchain.schema import StrOutputParser
from langchain.docstore.document import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup
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
def doc_sum(file_path: str) -> str:
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

    # print("[!] read doc file succ:", file_path)
    # agent query...
    
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
    # 先分析执行make时编译的伪目标，提取伪目标里面的所有编译目标文件
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
            logging.info(f"[+] Container {container_id} created.")
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
        self.execute_command("proxychains bash")

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
                    recv = self.session.recv(1024)
                    encode_result = chardet.detect(recv)
                    output += recv.decode(encoding=(encode_result["encoding"] if encode_result["encoding"] != None else "utf-8"),errors="ignore")
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
                output = output[:1500]+"\n......\n"+output[-1500:]
            return output

    def close(self):
        logging.info("[+] Stopping docker container, please wait a second...")
        if self.client:
            self.client.close()
        if self.container_id:
            subprocess.run(f"docker stop {self.container_id}", shell=True)
            subprocess.run(f"docker rm {self.container_id}", shell=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# RAG
class SearchCompilationInstruction:
    def __init__(self, directory_path: str, threshold=0.80):
        self.vectorstore = None
        self.similarity_threshold = threshold
        self.directory_path = directory_path
        # compilation instruction documents
        self.compilation_ins_doc = ["README","INSTALL"] + [file for root, dirs, files in os.walk(directory_path) for file in files if file.endswith(".md") or file.endswith(".txt")]
        # breakpoint()
        
    def read_files(self, to_read_docs: list) -> list:
        documents = []
        for root, dirs, files in os.walk(self.directory_path):
            for file in files:
                if file in to_read_docs:
                    file_path = os.path.join(root,file)
                    # breakpoint()
                    try:
                        with open(file_path,'r',errors="ignore") as fp:
                            content=fp.read()
                            documents.append(content)
                    except Exception as e:
                        print(f"Failed to read {file_path}: {e}")
        return [Document(page_content="".join(documents), metadata={"source":self.directory_path})]

    def setup_rag(self, files) -> bool:
        docs = self.read_files(to_read_docs=files)
        # split documents
        if docs != []:
            try:
                # TODO
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=3000, chunk_overlap=500, add_start_index=True
                )
                all_splits = text_splitter.split_documents(docs)
                breakpoint()
                self.vectorstore = Chroma.from_documents(
                    documents=all_splits,
                    embedding= OpenAIEmbeddings(
                        base_url="http://15.204.101.64:4000/v1",
                        model="text-embedding-3-large",
                        # api_key="sk-None-b4oAiUW1ZrrNSgDBwclvT3BlbkFJxNVWAD4Cr2kuiN5Sf0b8",
                        api_key="sk-UGOp2ky29JpDCoft0267C7Ac37F34224B06cC1E507C80aA7",
                        http_client=httpx.Client(proxies="socks5://127.0.0.1:29999"),
                        timeout=60
                    )
                )
                return True
            except Exception as e:
                return False
        return False
    
    def get_relevant_docs(self, query: str):
        docs_and_scores = self.vectorstore.similarity_search_with_score(query) # 用关键词查
        relevant_docs = [
            Document(page_content=doc.page_content,metadata=doc.metadata)
            for doc, score in docs_and_scores
            if score >= self.similarity_threshold
        ]
        return relevant_docs, len(relevant_docs)

    def search_instruction(self, query: str) -> str:
        """
        Retrive the section about the query from the project documentation 
        @param query: The query question.
        """
        rag = self.setup_rag(files=self.compilation_ins_doc)
        # breakpoint()
        if rag:
            # retriver = self.vectorstore.as_retriever(search_type="similarity",search_kwargs={"k":6})
            docs, found_relevant = self.get_relevant_docs(query)
            # breakpoint()
            if found_relevant:
                llm = ChatOpenAI(
                    base_url="http://15.204.101.64:4000/v1",
                    model="gpt-3.5-turbo",
                    # api_key="sk-None-b4oAiUW1ZrrNSgDBwclvT3BlbkFJxNVWAD4Cr2kuiN5Sf0b8",
                    api_key="sk-UGOp2ky29JpDCoft0267C7Ac37F34224B06cC1E507C80aA7",
                    http_client=httpx.Client(proxies="socks5://127.0.0.1:29999")
                )
                template = """You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
                Question: {question}
                Context: {context} 
                Answer:
                """
                context = "\n".join(doc.page_content for doc in docs)
                prompt = PromptTemplate.from_template(template=template)
                rag_chain=(
                    {"context":RunnableLambda(lambda x :context), "question":RunnablePassthrough()}
                    | prompt
                    | llm
                    | StrOutputParser()
                )
                answer = rag_chain.invoke(query)
                return answer
        return "Sorry, there is no compilation guidance in the project."
    
# Keyword
class SearchInstruction:
    def __init__(self, directory_path):
        self.directory_path = directory_path
        self.keywords = ["compile","build"]
        self.selected_chunks = []
        # compilation instruction documents
        self.compilation_ins_doc = ["README","INSTALL"] + [file for root, dirs, files in os.walk(directory_path) for file in files if file.endswith(".md") or file.endswith(".txt")]

    def read_files(self, to_read_docs: list) -> list:
        documents = []
        for root, dirs, files in os.walk(self.directory_path):
            for file in files:
                if file in to_read_docs:
                    file_path = os.path.join(root,file)
                    # breakpoint()
                    try:
                        with open(file_path,'r',errors="ignore") as fp:
                            content=fp.read()
                            documents.append(content)
                    except Exception as e:
                        print(f"Failed to read {file_path}: {e}")
        return [Document(page_content="".join(documents), metadata={"source":self.directory_path})]

    def select_chunks(self, files):
        docs = self.read_files(to_read_docs=files)
        # split documents
        if docs != []:
            try:
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000, chunk_overlap=50, add_start_index=True
                )
                all_splits = text_splitter.split_documents(docs)
                # breakpoint()
                for keyword in self.keywords:
                    for chunk in all_splits:
                        if keyword in chunk.page_content:
                            self.selected_chunks.append(chunk)
                # breakpoint()
                if len(self.selected_chunks)!=0:
                    return True
            except Exception as e:
                return False
        return False

    def search_instruction(self,*args,**kwargs) -> str:
        found = self.select_chunks(self.compilation_ins_doc)
        if found:
            try:
                llm = ChatOpenAI(
                        base_url="http://15.204.101.64:4000/v1",
                        model="gpt-3.5-turbo",
                        # api_key="sk-None-b4oAiUW1ZrrNSgDBwclvT3BlbkFJxNVWAD4Cr2kuiN5Sf0b8",
                        api_key="sk-UGOp2ky29JpDCoft0267C7Ac37F34224B06cC1E507C80aA7",
                        http_client=httpx.Client(proxies="socks5://127.0.0.1:29999")
                    )
                template = """You are an assistant skilled in extracting compilation commands. Use the following pieces of text to identify the compilation command. If no compilation command is found, look for a URL related to compilation and output: <url>. If you can't find either, just say that you don't know. Response should be brief, clear, and professional.
                Text: {text} 
                Answer:
                """
                text = "\n".join(chunk.page_content for chunk in self.selected_chunks)
                prompt = PromptTemplate.from_template(template=template)
                rag_chain=(
                    {"text":RunnableLambda(lambda x :text)}
                    | prompt
                    | llm
                    | StrOutputParser()
                )
                answer = rag_chain.invoke({})
                return answer
            except openai.BadRequestError:
                return "The length of the prompt has exceeded the maximum input length of the model and I can't find the compilation guidance in the project."
        return "There is no compilation guidance in the project."


    def __init__(self, directory_path: str):
        self.directory_path = directory_path
        self.compilation_tar_doc = ["Makefile"]

    def display_info(self,tar=False):
        if tar:
            return self.compilation_tar_doc

    def read_files(self, to_read_docs: list) -> list:
        documents = []
        for root, dirs, files in os.walk(self.directory_path):
            for file in files:
                if file in to_read_docs:
                    file_path = os.path.join(root,file)
                    # breakpoint()
                    try:
                        with open(file_path,'r',errors="ignore") as fp:
                            content=fp.read()
                            documents.append(content)
                    except Exception as e:
                        print(f"Failed to read {file_path}: {e}")
        return documents
    
    def search_target(self,*args,**kwargs):
        """
        Read the Makefile file and return the final target file.
        This function doesn't take any arguments.
        """
        docs = self.read_files(to_read_docs=self.compilation_tar_doc)
        if len(docs) != 0: 
            content = "\n".join(doc for doc in docs)
            llm = ChatOpenAI(
                base_url="https://api.fireworks.ai/inference/v1",
                # api_key="GlxjqIOfuG5gzXebVZpG9gRjlCV4rs7ZxocvyoSUwebeh6AX",
                api_key="0oEnOl0go9swJRhuhgefQr94J3Gtzbikmz8i9XqBrbDCO3z7",
                model="accounts/fireworks/models/mixtral-8x7b-instruct",
                temperature=0
            )
            prompt = PromptTemplate(
                template="""
                You are an expert in analyzing Makefiles and identifying compilation outputs. Your task is to analyze the provided Makefiles and extract only the final compiled targets.

                Please follow these steps:

                First analyze the pseudo target in the makefile file and extract all the compiled target files in the pseudo target.
                List only these final output files.
                Input:
                {Makefile}

                Output:

                Final compiled target files:
                """,
                input_variables=["Makefile"]
            )
            chain = prompt | llm | StrOutputParser()
            # breakpoint()
            try:
                answer = chain.invoke({"Makefile":content})
                return answer
            except Exception as e:
                return "Sorry, there are not the final compilation files." #todo
        return "Sorry, the project don't have the Makefile."

class SearchTarget:
    def __init__(self) -> None:
        self.logger = []
        
    def search_target(self, file_path, *args, **kwargs):
        """
        Retrieve the final compiled target file from the param file_path after the compilation.
        @param file_path: The absolute path of the project
        """
        local_path = os.environ["LOCAL_PATH"]
        file_path=file_path.replace("/work",local_path)
        if file_path.endswith("\n"):
            file_path=file_path[:-1]
        # breakpoint()
        with open(file_path,"r") as fp:
            docs=fp.read()
        
        # print(docs)
        # print("="*100)

        llm = ChatOpenAI(
            base_url="https://api.fireworks.ai/inference/v1",
            # api_key="GlxjqIOfuG5gzXebVZpG9gRjlCV4rs7ZxocvyoSUwebeh6AX",
            api_key="0oEnOl0go9swJRhuhgefQr94J3Gtzbikmz8i9XqBrbDCO3z7",
            model="accounts/fireworks/models/mixtral-8x7b-instruct",
            temperature=0
        )
        prompt = PromptTemplate(
            template="""
            You are an expert in analyzing Makefiles and identifying compilation outputs. Your task is to analyze the provided Makefiles and extract only the final compiled targets.

            Please follow these steps:

            1. analyze the pseudo target in the makefile file.
            2. extract all the compiled target files in the pseudo target.
            3. List only these final output files.
            Input:
            {Makefile}

            Output:

            Final compiled target files:
            """,
            input_variables=["Makefile"]
        )
        chain = prompt | llm | StrOutputParser()
        # breakpoint()
        try:
            answer = chain.invoke({"Makefile":docs})
            return answer
        except Exception as e:
            return "Sorry, there are not the final compilation files." #todo

if __name__ == '__main__':
    # DEMO
    search_ins = SearchInstruction(directory_path="/data/huli/CompileAgent/dataset/redis")
    answer = search_ins.search_instruction(query="how to compile the project?")
    print(answer)
    # with InteractiveDockerShell(local_path="/data/huli/CompileAgent/dataset/tiny-AES-c") as shell:
    #     print("="*60)
    #     print(shell.execute_command('tree /work/ -L 2'))
    #     print("="*60)
    #     print(shell.execute_command('sleep 3 ; echo "hello"'))
    #     print("="*60)
    #     print(shell.execute_command('ls'))
    #     print("="*60)
    #     print(shell.execute_command('gcc -v'))
    #     print("="*60)
    #     print(shell.execute_command('uname -a'))
    #     print("="*60)


