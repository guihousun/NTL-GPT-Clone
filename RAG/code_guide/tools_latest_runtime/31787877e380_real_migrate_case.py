from storage_manager import storage_manager
p=storage_manager.resolve_output_path("real_migrate.csv", thread_id="debug")
open(p,"w",encoding="utf-8").write("v\n1\n")
print("WROTE",p)
