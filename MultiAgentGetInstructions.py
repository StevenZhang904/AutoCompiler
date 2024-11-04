from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableLambda
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain.schema import SystemMessage, HumanMessage, AIMessage, StrOutputParser
from typing import List, Dict
from langchain.docstore.document import Document
from langchain.agents import AgentExecutor, Tool
from langchain.agents import create_react_agent
from config import *
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time 
import requests
import os

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT_GETINSTRUCTIONS

class ConversationAgent:
    def __init__(self, content):
        self.chat = ChatOpenAI(
            base_url=OPENAI_BASE_URL,
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            temperature=1
        )
        self.conversation_history: List = [
            SystemMessage(content=content)
        ]
    
    def receive_message(self, message: str, sender: str):
        self.conversation_history.append(HumanMessage(content=f'{sender}: {message}'))

    def send_message(self) -> str:
        response = self.chat.invoke(self.conversation_history)
        self.conversation_history.append(AIMessage(content=response.content))
        return response.content
    
class AgentTools:
    def __init__(self, proxy, project_name):
        self.use_proxy=proxy
        self.project_name = project_name

    def get_content_from_files(self, file_path):
        """
        Read the content of files which may exists compilation/building instructions.
        @param file_path: the location of the file.
        """
        try:
            if not isinstance(file_path, str):
                return "Error: file_path must be a string"
            file_path = file_path.strip()

            for wrapper in ['**','`','"',"'"]:
                if file_path.startswith(wrapper) and file_path.endswith(wrapper):
                    file_path = file_path[len(wrapper):-len(wrapper)]
                if file_path.startswith(wrapper):
                    file_path = file_path[len(wrapper):]
                if file_path.endswith(wrapper):
                    file_path = file_path[:-len(wrapper)]

            base_path = f"dataset/{self.project_name}"
            if file_path.startswith(base_path):
                file_path = file_path[len(base_path):].lstrip('/')

            full_path = os.path.join(base_path,file_path)
            if not os.path.exists(full_path):
                return f"Error: File not found at path: {full_path}"
            
            with open(full_path,'r') as fp:
                content=fp.read()

            if len(content) > 32000:
                content = content[:32000] + "\n... (content truncated due to length)"
            
            if not content.strip():
                return "File is empty"
            
            return content
        except Exception as e:
            error_message = f"Error reading file {file_path}: {str(e)}"
            return error_message
        
    def get_url_from_files(self, file_path):
        """
        Retrieve the URL associated with the compilation/building instructions.
        @param file_path: the location of the file.
        """
        content = self.get_content_from_files(file_path)
        if content:
            try:
                llm = ChatOpenAI(
                    base_url=DEEPSEEK_BASE_URL,
                    api_key=DEEPSEEK_API_KEY,
                    model=DEEPSEEK_MODEL,
                    temperature=1,
                )
                template = """You are an experienced software development engineer and specialized in identifying URLs related to compilation commands. Analyze the given text and extract any URLs specifically associated with obtaining or referencing compilation instructions. If no relevant URLs are found, simply state 'No relevant URLs found.' Ensure the result is accurate, concise, and professional.
                Text: {text}
                Answer:"""
                prompt = PromptTemplate.from_template(template=template)
                chain = (prompt | llm | StrOutputParser())
                answer = chain.invoke({"text":content})
                return answer
            except Exception as e:
                return "Search failed due to unknown reason."
        return "Not found any relevant URL from files stored in the local path."
        
    def get_content_from_url(self, url):
        """
        Get the web page content from the corresponding url.
        @param url: the URL of the content you want to get
        """
        ua = UserAgent()
        headers = {
            "User-Agent": ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        proxies = {
            "http": self.use_proxy,
            "https": self.use_proxy
        }

        try:
            response = requests.get(url,headers=headers,proxies=proxies)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            texts = soup.get_text(separator="\n",strip=True)
            return texts
        except Exception as e:
            return f"Request url error: {url}"
    

class GetInstructions:
    def __init__(self, project_name):
        self.logger = []
        self.project_name = project_name

    def create_agent_executor(self, conversation_memory, proxy=PROXY):
        llm = ChatOpenAI(
            base_url=DEEPSEEK_BASE_URL,
            api_key=DEEPSEEK_API_KEY,
            model=DEEPSEEK_MODEL,
            temperature=1
        )
        agenttools = AgentTools(proxy=proxy ,project_name=self.project_name)
        tools = [
            Tool(
                name='GET_CONTENT_FROM_FILES',
                description=agenttools.get_content_from_files.__doc__,
                func=agenttools.get_content_from_files
            ),
            Tool(
                name='GET_URL_FROM_FILES',
                description=agenttools.get_url_from_files.__doc__,
                func=agenttools.get_url_from_files
            ),
            Tool(
                name='GET_CONTENT_FROM_URL',
                description=agenttools.get_content_from_url.__doc__,
                func=agenttools.get_content_from_url
            )
        ]
        prompt=PromptTemplate.from_template(template="""You are an experienced software development engineer specialized in building projects from source code.
    Previous Conversation Context:
    {chat_history}

    Available Tools:
    {tools}

    Current Task: {input}

    To approach this step-by-step:
    1. First, analyze the given files using GET_CONTENT_FROM_FILES
    2. Look for any relevant URLs using GET_URL_FROM_FILES
    3. If URLs are found, fetch their content using GET_CONTENT_FROM_URL
    4. Compile all information into clear build instructions

    Use this format:
    Thought: Consider what you know and what to do next
    Action: Tool to use, should be one of {tool_names}
    Action Input: Specific input for the tool
    Observation: Tool result
    ... (repeat Thought/Action/Observation as needed)
    Thought: I know what to recommend
    Final Answer: Compilation Instructions in a clear, concise and accurate format.

    Begin working:
    Thought: {agent_scratchpad}"""
    )

        agent = create_react_agent(llm=llm,tools=tools,prompt=prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            memory=conversation_memory,
            max_iterations=10,
            verbose=True
        )

    def get_instructions(self, project_structure):
        """
        Select the files to read and get the compilation instructions from it according to the structure of the project.
        @param project_structure: The project's structure.
        """
        role1="BuildSystemExpert"
        experise1="build systems and compilation tools"
        focus_areas1=["Makefile", "CMake", "Gradle", "Maven"]

        agent1 = ConversationAgent(
            content=f"""You are a {role1}, a specialist in {experise1}. Your focus areas are: {', '.join(focus_areas1)}"""
        )

        role2="ProjectStructureAnalyst"
        experise2="project organization and conventions"
        focus_areas2=["directory structures", "configuration files", "dependency management"]
        agent2 = ConversationAgent(
            content=f"""You are {role2}, a specialist in {experise2}. Your focus areas are: {', '.join(focus_areas2)}"""
        )

        agent1.receive_message(f"""These are the project {self.project_name} structure: {project_structure}.
                                Analyze the project structure and suggest the five possible locations for build/compilation instructions.
                                Consider:
                                1. Common file patterns in your expertise area
                                2. Project structure conventions
                                3. Framework-specific configurations
                                4. Dependencies and their management
                                
                                Format your response as:
                                [Primary suggestions with confidence score]
                                [Reasoning based on project structure]""", "System")
        message1 = agent1.send_message()

        agent2.receive_message(message1, role1)
        agent2.receive_message(f"""These are the project {self.project_name} structure: {project_structure}.
                                According to the structure of the project, combined with the analysis of {role1} and suggest the five possible locations for build/compilation instructions.
                                Consider:
                                1. Common file patterns in your expertise area
                                2. Project structure conventions
                                3. Framework-specific configurations
                                4. Dependencies and their management
                                
                                Format your response as:
                                [Primary suggestions with confidence score]
                                [Reasoning based on project structure]""", "System")
        message2 = agent2.send_message()

        agent1.receive_message(message2, role2)
        agent1.receive_message(f"""Combined with the analysis results of {role2}, modify your own results, and finally select the files where the three compilation instructions are most likely to exist. The results must be professional, concise, and accurate. Note: output the files' path.
                                Output Format:
                                1. [Most possible location]
                                2. [Second possible location]
                                3. [Third possible location]""", "System")
        message3 = agent1.send_message()

        memory = ConversationBufferMemory(memory_key='chat_history', return_messages=True)
        for message in agent1.conversation_history:
            memory.chat_memory.add_message(message)

        question = f"""Analyze the provided files and determine the compilation/building instructions for the {self.project_name} project.
        Focus on Linux-based compilation methods and include any relevant URLs found.
        Please provide clear, concise and accurate complation/building instructions.
        Note: No additional Texts"""
        agent_executor = self.create_agent_executor(conversation_memory=memory)
        answer = agent_executor.invoke({"input":question})
        self.logger.append([
            project_structure,
            answer['output']
        ])
        return answer['output']
