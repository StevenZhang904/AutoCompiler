# langsmith config
LANGCHAIN_TRACING_V2=""
LANGCHAIN_PROJECT=""
LANGCHAIN_PROJECT_GETINSTRUCTIONS=""
LANGCHAIN_PROJECT_RECONCILE=""

LANGCHAIN_API_KEY=""
# baselines
LANGCHAIN_PROJECT_READMEAI=""
LANGCHAIN_PROJECT_RAG=""
# agent strategy
LANGCHAIN_PROJECT_REACT=""
LANGCHAIN_PROJECT_PLANANDEXECUTE=""
LANGCHAIN_PROJECT_OPENAIFUNC=""

# huli
SERPER_API_KEY=""
LOG_URL_TEMPLATE=""

# qwen
QWEN_BASE_URL=""
QWEN_MODEL=""
QWEN_API_KEY=""
QWEN_READMEAI_API_KEY=""
QWEN_RAG_API_KEY=""

## Multi-Agent Discussion
# openai
OPENAI_BASE_URL=""
OPENAI_MODEL=""
OPENAI_EMBEDDING_MODEL=""
OPENAI_API_KEY="" 

# claude
ANTHROPIC_BASE_URL=""
ANTHROPIC_MODEL=""
ANTHROPIC_API_KEY=""

# deepseek
DEEPSEEK_BASE_URL=""
DEEPSEEK_MODEL=""
DEEPSEEK_API_KEY=""
DEEPSEEK_RAG_API_KEY=""
DEEPSEEK_READMEAI_API_KEY=""

# readmeai 
READMEAI_BASE_URL=""
READMEAI_API_KEY=""
READMEAI_MODEL=""
READMEAI_DIR=""

PROXY=""
PASSWORD=""

# logs
PROCESS_LOG_CSV_PATH=""
FLOW_BASED_LOG_CSV_PATH=""

# baselines
READMEAI_LOG_CSV_PATH=""
RAG_LOG_CSV_PATH=""
# different agent strategy
REACT_LOG_CSV_PATH=""
PLANANDEXECUTE_LOG_CSV_PATH=""
OPENAIFUNC_LOG_CSV_PATH=""

# ablation study
FILE_NAVIGATOR_LOG_CSV_PATH=""
INSTRUCTION_EXTRACTOR_LOG_CSV_PATH=""
WEBSITE_SEARCH_LOG_CSV_PATH=""
MULTIAGENT_DISCUSSION_LOG_CSV_PATH=""

# to compile projects
COMPILE_PROJECTS_PATH=""

# ========================== agent config ==========================
template = """You are an experienced software development engineer. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [ {tool_names} ]
Action Input: the input to the action, do not explain the input further
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)

Thought: I now know the final answer
Final Answer: the final answer to the original input question


Begin!
Question: {input}

Thought:{agent_scratchpad}"""


model_decision_template = """I want you to help me compile the project {project_name} from source code. Please complete the compilation task step by step.

The project has been downloaded into /work/, which is also the Shell's initial path.
You should follow these rules:
1. Use the Shell tool to execute any command for compilation, and it is recommended to use `tree . -L 2` command to show the project structure.
2. Use the CompileNavigator tool to looking for compilation instructions. Try to avoid reading documents in Shell tool, unless you think it's necessary.
3. If there are any difficulties during compilation, try to break them without calling tools.
4. Unless you encounter a problem that you cannot solve, there is no need to call the ErrorSolver tool.
5. No need to install this project or test it, just compile it.
6. Compilation target should be the main body of the project, for example, the executable programs for a tool-type project or the shared/static libraries for a library project.
7. When you've done your best, you need to check if the project actually compiled successfully and output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""


rag_template = """You are an experienced software development engineer. I want you help me compile {project_name} project from source code. Please complete the compilation task step by step, use the tools provided if require (one tool each time).

The project has been downloaded into /work/, which is also the SHELL's initial path, use the SHELL tool to execute the compilation command.
The following steps must be followed:
1. Use the SEARCH_INSTRUCTION_FROM_FILES tool to obtain the compilation command and proceed to step 3 if the command is found.
2. Use the SEARCH_URL tool to locate a URL related to the compilation guidance. If a URL is found, use the SEARCH_INSTRUCTION_FROM_URL tool to get the compilation command, and continue to step 3 if there are compilation commands.
3. Use the SHELL tool to execute any command for compilation, and needn't install this project or test it, just compile it.
4. During the compilation process, attempt to resolve any encountered issues until the process completes successfully.
5. Compilation target is the main body of the project, for example, the executable programs for a tool-type project or the shared/static libraries for a library project.
6. When you've done your best, you need to check if the project actually compiled successfully and output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""

readmeai_template = """You are an experienced software development engineer. I want you to help me compile the project {project_name} from source code. Please complete the compilation task step by step, use the tools provided if require (one tool each time).

The project has been downloaded into /work/, which is also the SHELL's initial path.
You should follow these rules:
1. Use the READMEAI tool to obtain the compilation commands.
2. Use the SHELL tool to execute any command for compilation.
3. If there are any difficulties during compilation, try to break them.
4. No need to install this project or test it, just compile it.
5. Compilation target should be the main body of the project, for example, the executable programs for a tool-type project or the shared/static libraries for a library project.
6. When you've done your best, you need to check if the project actually compiled successfully and output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""

discussion_template1="""You are an experienced compiler troubleshooting expert. Your task is to analyze provided error messages, identify likely causes, and deliver specific solutions. 

The entire compilation process was performed on Ubuntu 22.04 with root user.
the error messages during {project} compilation are as follows:
{input}

Unless you really don't know how to solve this problem, there is no need to call the following tools:
{tools}

Output the answer in JSON format as follows (Strict JSON, NO Additional Text):
{{
    "reasoning": "Concise explanation of problem-solving process",
    "solution": "Specific instructions, requiring conciseness, professionalism and accuracy(No additional relevant texts)",
    "confidence_level": <numeric confidence between 0.0 and 1.0>
}}

Begin!
"""

discussion_template1_without_tools="""You are an experienced compiler troubleshooting expert. Your task is to analyze provided error messages, identify likely causes, and deliver specific solutions. 

The entire compilation process was performed on Ubuntu 22.04 with root user.
the error messages during {project} compilation are as follows:
{input}

Output the answer in JSON format as follows (Strict JSON, NO Additional Text):
{{
    "reasoning": "Concise explanation of problem-solving process",
    "solution": "Specific instructions, requiring conciseness, professionalism and accuracy(No additional relevant texts)",
    "confidence_level": <numeric confidence between 0.0 and 1.0>
}}

Begin!
"""

discussion_template2="""You are an experienced compiler troubleshooting expert. Your task is to analyze provided error messages, identify likely causes, and deliver specific solutions.

The entire compilation process was performed on Ubuntu 22.04 with root user.
the error messages during {project} compilation are as follows:
{input}

Unless you really don't know how to solve this problem, there is no need to call the following tools:
{tools}

Carefully review the following solutions from other agents as additional information, and provide your own answer. Clearly states that which pointview do you agree or disagree and why.
{chat_history}

Output the answer in JSON format as follows (Strict JSON, NO Additional Text):
{{
    "reasoning": "Concise explanation of problem-solving process",
    "solution": "Specific instructions, requiring conciseness, professionalism and accuracy(No additional relevant texts)",
    "confidence_level": <numeric confidence between 0.0 and 1.0>
}}

Begin!
"""

get_instructions_template="""You are an experienced software development engineer. I want you to help me find out the project {project_name} compilation instructions. Please complete the searching task step by step, use the tools provided if require (one tool each time).

Project structure: {project_structure}

You should follow these rules:
1. Analyze the given project structure and reference the document file which exists compilation instructions, and then use DEBATE tool to check it.
2. Use the SEARCH_INSTRUCTIONS_FROM_FILES tool to looking for compilation instructions within the file inferred in the previous step. 
3. If URLs are found, fetch their content using GET_CONTENT_FROM_URL.
4. Compile all information into clear compilation instructions, do not include test commands.
5. Keep the instructions concise, professional and accurate.
"""

# different agent strategy
# ===============================================
planandexecute_template="""
Plan:
1. Use the SHELL tool to navigate to the project directory and execute the `tree . -L 2` command to show the project structure.\nUse the GET_INSTRUCTIONS tool to look for compilation instructions within the project and if no compilation instructions are found, then try to find the instructions without calling tools.\nUse the SHELL tool to execute the compilation command based on the instructions found. If there are any difficulties during compilation, attempt to resolve them without calling additional tools, then use the RECONCILE tool to address the issue.\nAfter attempting to compile, check if the project compiled successfully by verifying the presence of the expected output files (e.g., executables or libraries).\nGiven the above steps taken, please respond to the user\'s original question with either COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN.

<END_OF_PLAN>
"""

react_template="""I want you to help me compile the project {project_name} from source code. Please complete the compilation task step by step, invoke the tools when you need them, rather than guessing the answer.

The project has been downloaded into /work/, which is also the SHELL's initial path.
It is recommanded to use `ls` command to show the project composition.
When you've done your best, you need to check if the project actually compiled successfully and output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""

openaifunc_template="""You are an experienced software development engineer. I want you to help me compile the project {project_name} from source code. Please complete the compilation task step by step, use the tools provided if require (one tool each time).

The project has been downloaded into /work/, which is also the SHELL's initial path.
It is recommanded to use `ls` command to show the project composition.
When you've done your best, you need to check if the project actually compiled successfully and output COMPILATION-SUCCESS, COMPILATION-FAIL, or COMPILATION-UNCERTAIN as the final answer.
"""