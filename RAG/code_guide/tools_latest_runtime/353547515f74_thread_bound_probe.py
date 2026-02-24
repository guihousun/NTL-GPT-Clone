from storage_manager import storage_manager, current_thread_id
current_thread_id.set('debug')
print(storage_manager.resolve_output_path('thread_bound_probe.csv'))
