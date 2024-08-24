# An LLM-Agent for project compilation automatically


## requirements

`pip install langchain -i https://pypi.tuna.tsinghua.edu.cn/simple`
`pip install typing-inspect==0.8.0 typing_extensions==4.5.0 -i https://pypi.tuna.tsinghua.edu.cn/simple`

## Usage

`python CompileAgent.py`

## Roadmap

- [x] better logging
- [x] command logging for replay
- [x] add a uncertain option to model final output
- [ ] use LLM to get the final binary name, and check it **@HuLi** tools.py@makefile_reader
- [ ] use LLM to get compilation instruction from docs **@HuLi** tools.py@doc_sum
- [x] better command tool
- [x] build a better docker image, add a dockerfile

- [x] download the project source code **@chenye**

Future works
- support specific compilation options
    - [x] optimization level
    - [x] debug info
    - [ ] compiler
    - [ ] target platform


# Workflow

1. download the project source code (python)
2. find doc (agent)
3. call doc_sum (agent)
4. find compilation instruction, return concise doc (doc_sum)
5. try compilation (agent)
6. call makefile_reader (agent)
7. find the target binary name (makefile_reader)
8. checkout (agent)
9. log agent-checkout-result, log checker-resulst (if have) (python)

inst in project (ok)
inst not in project
 - read readme.md 
 - get url
