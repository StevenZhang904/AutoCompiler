# An LLM-Agent for project compilation automatically


## requirements

`pip install langchain -i https://pypi.tuna.tsinghua.edu.cn/simple`
`pip install typing-inspect==0.8.0 typing_extensions==4.5.0 -i https://pypi.tuna.tsinghua.edu.cn/simple`

## Usage

`python CompileAgent.py`

## Roadmap

- [ ] better logging
- [x] command logging for replay
- [x] add a uncertain option to model final output
- [ ] use LLM to get the final binary name, and check it **@HuLi** tools.py@makefile_reader
- [ ] use LLM to get compilation instruction from docs **@HuLi** tools.py@doc_sum
- [x] better command tool
- [x] build a better docker image, add a dockerfile

Future works
- support specific compilation options
    - [x] optimization level
    - [x] debug info
    - [ ] compiler
    - [ ] target platform



