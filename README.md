# CompileAgent: Automated Real-World Repo-Level Compilation with Tool-Integrated LLM-based Agent System

## Environment Setup
```python
conda create -n CompileAgent python=3.9.0
conda activate CompileAgent
pip install -r requirements.txt
```

## Usage
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

