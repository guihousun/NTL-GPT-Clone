import ast
import json
import os
import sys

def get_stdlib_modules():
    return set(sys.builtin_module_names) | {
        'os', 'sys', 'json', 'time', 'datetime', 'math', 're', 'shutil', 'subprocess', 'logging', 
        'argparse', 'collections', 'io', 'pathlib', 'typing', 'enum', 'copy', 'tempfile', 'warnings', 
        'glob', 'pickle', 'ast', 'platform', 'inspect', 'functools', 'contextlib', 'threading', 
        'multiprocessing', 'concurrent', 'urllib', 'http', 'email', 'abc', 'dataclasses', 'uuid', 
        'random', 'statistics', 'hashlib', 'base64', 'gzip', 'zipfile', 'tarfile', 'csv', 'sqlite3', 
        'unittest', 'doctest', 'pdb', 'profile', 'pstats', 'trace', 'traceback', 'faulthandler', 
        'gc', 'weakref', 'pprint', 'code', 'codeop', 'site', 'sysconfig', 'distutils', 'xml', 'html', 
        'wsgiref', 'xmlrpc', 'socket', 'ssl', 'select', 'selectors', 'asyncio', 'signal', 'mmap', 
        'ctypes', 'struct', 'array', 'bisect', 'heapq', 'queue', 'dbm', 'shelve', 'marshal', 'zlib', 
        'lzma', 'bz2', 'binascii', 'quopri', 'uu', 'binhex', 'fnmatch', 'linecache', 'filecmp', 
        'shlex', 'tokenize', 'token', 'keyword', 'symbol', 'py_compile', 'compileall', 'dis', 
        'textwrap', 'locale', 'gettext', 'string', 'difflib', 'numbers', 'decimal', 'fractions', 
        'cmath', 'operator', 'calendar', 'contextvars'
    }

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
        pass
    return imports

def scan_codebase_imports():
    root_dir = os.getcwd()
    all_imports = set()
    exclude_dirs = {'.git', '.vscode', '__pycache__', 'venv', 'env', '.trae', 'base_data', 'cache', 'user_data'}
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = os.path.join(dirpath, filename)
                all_imports.update(get_imports_from_file(filepath))
    
    stdlib = get_stdlib_modules() | {'importlib', '__future__'}
    return sorted(list(all_imports - stdlib))

def main():
    # 1. Load installed packages
    # Check if installed_packages.json exists, if not, try to generate it or fail
    if not os.path.exists('installed_packages.json'):
        print("Error: installed_packages.json not found. Run pip list --format=json > installed_packages.json first.")
        # Optional: could attempt to run the command here
        return

    try:
        with open('installed_packages.json', 'r', encoding='utf-16') as f:
            installed_list = json.load(f)
    except Exception:
        try:
            with open('installed_packages.json', 'r', encoding='utf-8') as f:
                installed_list = json.load(f)
        except Exception:
            with open('installed_packages.json', 'r') as f:
                installed_list = json.load(f)
    
    # Map lowercase package name to (real_name, version)
    installed_map = {pkg['name'].lower(): (pkg['name'], pkg['version']) for pkg in installed_list}

    # 2. Scan imports
    detected_imports = scan_codebase_imports()
    print(f"Detected imports: {detected_imports}")

    # 3. Mapping configuration
    import_mapping = {
        'PIL': 'pillow',
        'cv2': 'opencv-python',
        'dotenv': 'python-dotenv',
        'ee': 'earthengine-api',
        'skimage': 'scikit-image',
        'sklearn': 'scikit-learn',
        'yaml': 'PyYAML',
        'osgeo': 'GDAL',
        'google': 'google-api-python-client', # Heuristic, could be google-cloud-*
        'typing_extensions': 'typing-extensions',
        'streamlit_folium': 'streamlit-folium',
        # Langchain specifics
        'langchain_chroma': 'langchain-chroma',
        'langchain_community': 'langchain-community',
        'langchain_core': 'langchain-core',
        'langchain_experimental': 'langchain-experimental',
        'langchain_google_community': 'langchain-google-community',
        'langchain_openai': 'langchain-openai',
        'langchain_tavily': 'langchain-tavily',
        'langchain_text_splitters': 'langchain-text-splitters',
        'langgraph_supervisor': 'langgraph-supervisor',
    }

    requirements = []
    missing_imports = []

    # Always include these core packages if they are installed, even if not explicitly imported
    # (Sometimes imports are dynamic or handled via config)
    force_include = [
        'streamlit', 'langchain', 'langgraph', 'pandas', 'numpy', 'matplotlib'
    ]
    
    # Merge detected with force_include
    all_targets = set(detected_imports)
    for f in force_include:
        if f in installed_map: # Only if installed
            # Check if it's already covered by import mapping or direct name
            # Just add to all_targets as a potential import name
            all_targets.add(f)

    for imp in all_targets:
        # Ignore local modules (simple heuristic: if not in installed_map and not mapped)
        # But we need to check mapping first.
        
        pkg_name_guess = import_mapping.get(imp, imp)
        pkg_name_lower = pkg_name_guess.lower()
        
        # Strategy 1: Direct match
        if pkg_name_lower in installed_map:
            real_name, version = installed_map[pkg_name_lower]
            requirements.append(f"{real_name}=={version}")
            continue
            
        # Strategy 2: Hyphen replacement (common convention)
        pkg_name_hyphen = pkg_name_lower.replace('_', '-')
        if pkg_name_hyphen in installed_map:
            real_name, version = installed_map[pkg_name_hyphen]
            requirements.append(f"{real_name}=={version}")
            continue

        # Strategy 3: Underscore replacement
        pkg_name_underscore = pkg_name_lower.replace('-', '_')
        if pkg_name_underscore in installed_map:
            real_name, version = installed_map[pkg_name_underscore]
            requirements.append(f"{real_name}=={version}")
            continue

        # Strategy 4: Special Cases (Manual fallback checks)
        if imp == 'cv2' and 'opencv-python-headless' in installed_map:
             real_name, version = installed_map['opencv-python-headless']
             requirements.append(f"{real_name}=={version}")
             continue

        # Strategy 5: If import matches a known package prefix (e.g. google -> google-api-python-client)
        # We already handled this via import_mapping.

        # If we reach here, we likely can't find an installed package for this import.
        # It might be a local module.
        # Check if it exists as a .py file or directory in current root
        if os.path.exists(f"{imp}.py") or os.path.exists(imp):
            # It's a local module, skip
            continue
            
        missing_imports.append(imp)

    # Sort and Deduplicate
    requirements = sorted(list(set(requirements)), key=lambda x: x.lower())

    with open('requirements.txt', 'w') as f:
        f.write('\n'.join(requirements))
    
    print(f"Generated requirements.txt with {len(requirements)} packages.")
    if missing_imports:
        print(f"Skipped/Missing imports (likely local or uninstalled): {missing_imports}")

if __name__ == "__main__":
    main()
