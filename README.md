# 🤖CompileAgent: Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System

<p> 
  <a href="https://arxiv.org/pdf/2505.04254"><img src="https://img.shields.io/badge/🙏-Arxiv-red" height="20px"></a>
  <a href=""><img src="https://img.shields.io/badge/⭐-Post-blue" height="20px"></a>
  <a href=""><img src="https://img.shields.io/badge/😊-ACL'25-purple" height="20px"></a>
</p> 


## 📙About

CompileAgent is a tool designed to automatically compile projects directly from their source code repositories. In our [post](), we go beyond the scope of the paper by presenting extended experiments that highlight the application of CompileAgent across various downstream tasks.


## 🚀Environment Setup
```python
conda create -n CompileAgent python=3.9.0
conda activate CompileAgent
pip install -r requirements.txt
```

## 🔥Quick Start
`python CompileAgent.py --help`
```shell
Usage: CompileAgent.py [OPTIONS]

Compile the projects from source code with the help of AI assistant

Options:
  -j, --json_path TEXT the path to the project file to be compiled [required]
  -p, --dataset_base_path TEXT the base path to store the projects need to compile [required]
  -l, --log_path TEXT the path to store the logs of compilation [required]
  -c, --clean_copied_project BOOLEAN whether to clear the new project path after the compilation, set to True when debugging [required]
  -r, --retry INTEGER the times to retry when fail to pass checker
  -s, --strict_checker BOOLEAN if True, only return True when all target files are in the file list, otherwise return True when any target file is in the file list
  --download_proxy TEXT pass to git --config http.proxy=${}, e.g., socks5://127.0.0.1:29999, if do not set: do not use proxy
  --multi_process BOOLEAN whether to enable the multi-process to compile the projects
  --help Show this message and exit.
```

**NOTE:** Please configure the required LLMs api in `Config.py` before execting the `CompileAgent.py` file.

## 📜Citation
```
@misc{hu2025compileagentautomatedrealworldrepolevel,
  title={CompileAgent: Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System}, 
  author={Li Hu and Guoqiang Chen and Xiuwei Shang and Shaoyin Cheng and Benlong Wu and Gangyang Li and Xu Zhu and Weiming Zhang and Nenghai Yu},
  year={2025},
  eprint={2505.04254},
  archivePrefix={arXiv},
  primaryClass={cs.SE},
  url={https://arxiv.org/abs/2505.04254}, 
}
```