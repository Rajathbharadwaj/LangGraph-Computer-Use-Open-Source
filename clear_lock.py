from langgraph.store.postgres import PostgresStore

conn_string = 'postgresql://postgres:password@localhost:5433/xgrowth'
with PostgresStore.from_conn_string(conn_string) as store:
    user_id = 'user_34wsv56iMdmN9jPXo6Pg6HeroFK'
    progress_namespace = (user_id, 'discovery_progress')
    
    # Clear the lock by setting it to None
    store.put(progress_namespace, 'current', {})
    print('✅ Cleared stale scraping lock')
