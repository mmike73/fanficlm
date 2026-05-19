try:
    from app.services import rag_service
    print("rag_service attributes:", [x for x in dir(rag_service) if not x.startswith('_')])
except Exception as e:
    import traceback
    traceback.print_exc()