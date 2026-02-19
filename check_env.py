import importlib.metadata
import sys
import subprocess
import os

def get_installed_packages():
    return {dist.metadata['Name'].lower(): dist.version for dist in importlib.metadata.distributions()}

def check_dependencies():
    installed = get_installed_packages()
    
    # Map import name to package name
    # If not in this map, assume package name = import name (lowercased)
    import_mapping = {
        'PIL': 'pillow',
        'cv2': 'opencv-python',
        'dotenv': 'python-dotenv',
        'ee': 'earthengine-api',
        'skimage': 'scikit-image',
        'sklearn': 'scikit-learn',
        'yaml': 'pyyaml',
        'osgeo': 'gdal',
        'google': 'google-api-python-client', # Heuristic, could be others
        'langchain_chroma': 'langchain-chroma',
        'langchain_community': 'langchain-community',
        'langchain_core': 'langchain-core',
        'langchain_experimental': 'langchain-experimental',
        'langchain_google_community': 'langchain-google-community',
        'langchain_openai': 'langchain-openai',
        'langchain_tavily': 'langchain-tavily', # Verify this
        'langchain_text_splitters': 'langchain-text-splitters',
        'typing_extensions': 'typing-extensions',
    }
    
    # Required imports (from previous step)
    required_imports = [
        'IPython', 'PIL', 'cv2', 'dask', 'dotenv', 'ee', 'folium', 'geemap', 
        'geopandas', 'geopy', 'google', 'h5py', 'joblib', 'langchain', 
        'langchain_chroma', 'langchain_community', 'langchain_core', 
        'langchain_experimental', 'langchain_google_community', 'langchain_openai', 
        'langchain_tavily', 'langchain_text_splitters', 'langgraph', 
        'langgraph_supervisor', 'matplotlib', 'numpy', 'osgeo', 'osmnx', 
        'pandas', 'pmdarima', 'pydantic', 'pymannkendall', 'pyproj', 
        'pyresample', 'rasterio', 'requests', 'satpy', 'scipy', 'shapely', 
        'skimage', 'sklearn', 'statsmodels', 'streamlit', 'streamlit_folium', 
        'tqdm', 'typing_extensions', 'xarray', 'yaml'
    ]

    missing = []
    
    print("--- Checking Dependencies ---")
    for imp in required_imports:
        pkg_name = import_mapping.get(imp, imp).lower()
        
        # Special handling for opencv
        if pkg_name == 'opencv-python':
            if 'opencv-python' not in installed and 'opencv-python-headless' not in installed and 'opencv' not in installed:
                 missing.append(pkg_name)
                 print(f"[MISSING] {imp} (package: {pkg_name})")
            continue
            
        # Special handling for google
        if imp == 'google':
             # Skip strict check for 'google' as it's a namespace package
             continue

        # Special handling for osgeo (gdal)
        if imp == 'osgeo':
            if 'gdal' not in installed:
                missing.append('gdal')
                print(f"[MISSING] {imp} (package: gdal)")
            continue

        if pkg_name not in installed:
            # Try replacing underscores with hyphens
            pkg_name_hyphen = pkg_name.replace('_', '-')
            if pkg_name_hyphen not in installed:
                missing.append(pkg_name_hyphen)
                print(f"[MISSING] {imp} (package: {pkg_name_hyphen})")
            else:
                pass
                # print(f"[OK] {imp} -> {pkg_name_hyphen} ({installed[pkg_name_hyphen]})")
        else:
            pass
            # print(f"[OK] {imp} -> {pkg_name} ({installed[pkg_name]})")

    return missing

def create_snapshot(filename):
    print(f"Creating snapshot: {filename}")
    try:
        # Use pip freeze for snapshot
        subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=open(filename, 'w'), check=True)
    except Exception as e:
        print(f"Error creating snapshot: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        snapshot_file = sys.argv[1]
    else:
        snapshot_file = "env_snapshot_current.txt"
        
    create_snapshot(snapshot_file)
    
    missing = check_dependencies()
    
    if missing:
        print("\n--- Missing Packages ---")
        for p in missing:
            print(p)
        
        # Write missing to file for easy reading
        with open('missing_deps.txt', 'w') as f:
            for p in missing:
                f.write(p + '\n')
    else:
        print("\nAll dependencies are satisfied.")
