import sys
import os
import json
import traceback
import importlib.util

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def _load_module_from_path(module_name: str, file_path: str):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec for {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

try:
    code_gen_mod = _load_module_from_path(
        "ntl_code_generation",
        os.path.join(os.path.dirname(__file__), "..", "tools", "NTL_Code_generation.py"),
    )
    knowledge_mod = _load_module_from_path(
        "geocode_knowledge_tool",
        os.path.join(os.path.dirname(__file__), "..", "tools", "geocode_knowledge_tool.py"),
    )
    GeoCode_COT_Validation_tool = code_gen_mod.GeoCode_COT_Validation_tool
    final_geospatial_code_execution_tool = code_gen_mod.final_geospatial_code_execution_tool
    GeoCode_Knowledge_Recipes_tool = knowledge_mod.GeoCode_Knowledge_Recipes_tool
except Exception as e:
    print(f"ImportError: {e}")
    traceback.print_exc()
    sys.exit(1)

def test_geocode_cot_validation():
    print("\nTesting GeoCode_COT_Validation_tool...")
    
    # Test case 1: Simple print (Should pass)
    code_pass = "print('Hello from GeoCode_COT_Validation')"
    try:
        result = GeoCode_COT_Validation_tool.invoke({"code_block": code_pass})
        print(f"Result (Pass Case): {result}")
        res_json = json.loads(result)
        if res_json['status'] == 'pass':
            print("  -> PASS verified")
        else:
            print("  -> FAIL (Unexpected)")
    except Exception as e:
        print(f"  -> Exception: {e}")
        traceback.print_exc()

    # Test case 2: Syntax Error (Should fail)
    code_fail = "print('Unclosed string"
    try:
        result = GeoCode_COT_Validation_tool.invoke({"code_block": code_fail})
        print(f"Result (Fail Case): {result}")
        res_json = json.loads(result)
        if res_json['status'] == 'fail':
            print("  -> FAIL verified (Expected)")
        else:
            print("  -> PASS (Unexpected)")
    except Exception as e:
        print(f"  -> Exception: {e}")
        traceback.print_exc()
        
    # Test case 3: GEE usage
    print("\nTesting GEE usage...")
    code_gee = "import ee\nprint(ee.String('GEE Working').getInfo())"
    try:
        result = GeoCode_COT_Validation_tool.invoke({"code_block": code_gee})
        print(f"Result (GEE Case): {result}")
        res_json = json.loads(result)
        if res_json['status'] == 'pass':
             print("  -> GEE PASS verified")
        else:
             print("  -> GEE FAIL (Likely auth/project issue, which is expected if not configured)")
    except Exception as e:
        print(f"  -> Exception: {e}")

def test_final_code_execution():
    print("\nTesting final_geospatial_code_execution_tool...")
    
    # Test case 1: Simple execution
    code_exec = "x = 10\ny = 20\nprint(f'Sum is {x+y}')"
    try:
        result = final_geospatial_code_execution_tool.invoke({"final_geospatial_code": code_exec})
        print(f"Result: {result}")
        res_json = json.loads(result)
        if res_json['status'] == 'success':
            print("  -> SUCCESS verified")
        else:
            print("  -> FAIL (Unexpected)")
    except Exception as e:
        print(f"  -> Exception: {e}")
        traceback.print_exc()

def test_preflight_path_protocol():
    print("\nTesting preflight protocol enforcement...")
    bad_code = r"""
import pandas as pd
df = pd.read_csv('inputs/demo.csv')
df.to_csv('outputs/out.csv', index=False)
"""
    try:
        result = GeoCode_COT_Validation_tool.invoke({"code_block": bad_code, "strict_mode": True})
        print(f"Result (Path Protocol): {result}")
        res_json = json.loads(result)
        if res_json.get("status") == "fail" and res_json.get("error_type") == "PreflightError":
            print("  -> Preflight protocol check PASS")
        else:
            print("  -> Preflight protocol check FAIL")
    except Exception as e:
        print(f"  -> Exception: {e}")
        traceback.print_exc()

def test_geocode_recipe_tool():
    print("\nTesting GeoCode_Knowledge_Recipes_tool...")
    try:
        result = GeoCode_Knowledge_Recipes_tool.invoke({
            "query": "Use GEE to compute ANTL/TNTL by administrative districts and export CSV",
            "top_k": 2,
            "library_focus": "gee"
        })
        print(f"Result (Recipe Tool): {result}")
        res_json = json.loads(result)
        matches = res_json.get("matched_recipes", [])
        if len(matches) >= 1 and "code" in matches[0]:
            print("  -> Recipe retrieval PASS")
        else:
            print("  -> Recipe retrieval FAIL")
    except Exception as e:
        print(f"  -> Exception: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting tests...")
    # Check if we are in an IPython environment
    try:
        from IPython import get_ipython
        ip = get_ipython()
        if ip is None:
            print("WARNING: Not running in an IPython environment. Tools might fail.")
        else:
            print("Running in IPython environment.")
    except ImportError:
        print("WARNING: IPython not installed.")

    test_geocode_cot_validation()
    test_final_code_execution()
    test_preflight_path_protocol()
    test_geocode_recipe_tool()
    print("\nTests completed.")

