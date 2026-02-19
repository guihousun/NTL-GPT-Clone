import ast
import os
import sys

def get_stdlib_modules():
    return set(sys.builtin_module_names)

def get_imports_from_file(filepath):
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=filepath)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
    except Exception as e:
        # print(f"Error parsing {filepath}: {e}")
        pass
    return imports

def main():
    root_dir = os.getcwd()
    all_imports = set()
    
    # Exclude venv/env directories if any
    exclude_dirs = {'.git', '.vscode', '__pycache__', 'venv', 'env', '.trae', 'base_data', 'cache', 'user_data'}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = os.path.join(dirpath, filename)
                all_imports.update(get_imports_from_file(filepath))
    
    stdlib = get_stdlib_modules()
    # Add some common stdlib modules that might be missed depending on python version
    stdlib.update({'os', 'sys', 'json', 'time', 'datetime', 'math', 're', 'shutil', 'subprocess', 'logging', 'argparse', 'collections', 'io', 'pathlib', 'typing', 'enum', 'copy', 'tempfile', 'warnings', 'glob', 'pickle', 'ast', 'platform', 'inspect', 'functools', 'contextlib', 'threading', 'multiprocessing', 'concurrent', 'urllib', 'http', 'email', 'abc', 'dataclasses', 'uuid', 'random', 'statistics', 'hashlib', 'base64', 'gzip', 'zipfile', 'tarfile', 'csv', 'sqlite3', 'unittest', 'doctest', 'pdb', 'profile', 'pstats', 'trace', 'traceback', 'faulthandler', 'gc', 'weakref', 'pprint', 'code', 'codeop', 'site', 'sysconfig', 'distutils', 'xml', 'html', 'wsgiref', 'xmlrpc', 'socket', 'ssl', 'select', 'selectors', 'asyncio', 'signal', 'mmap', 'ctypes', 'struct', 'array', 'bisect', 'heapq', 'queue', 'dbm', 'shelve', 'marshal', 'zlib', 'lzma', 'bz2', 'binascii', 'quopri', 'uu', 'binhex', 'fnmatch', 'linecache', 'filecmp', 'shlex', 'tokenize', 'token', 'keyword', 'symbol', 'py_compile', 'compileall', 'dis', 'textwrap', 'locale', 'gettext', 'string', 'difflib', 'numbers', 'decimal', 'fractions', 'cmath', 'operator'})
    
    third_party_imports = sorted(list(all_imports - stdlib))
    
    print("DETECTED_IMPORTS_START")
    for imp in third_party_imports:
        print(imp)
    print("DETECTED_IMPORTS_END")

if __name__ == "__main__":
    main()
