from TuGraphClient import TuGraphClient

from app.core.validator.db_client import DB_Client


class TuGraphDBClient(DB_Client):
    def __init__(self):
        # params
        pass
    def _create_client(db_client_params: dict) -> 'TuGraphClient | None':
        """create a new TuGraphClient instance with retry logic."""
        try:
            client = TuGraphClient(**db_client_params)
            try: 
                client.call_cypher("RETURN 1", timeout=5)
                print("Successfully created/reconnected TuGraphClient.")
                return client
            except Exception as e:
                print(f"Failed to execute test query on TuGraphClient: {e}")
                print(e)
        except Exception as e:
            print(f"Failed to create/reconnect TuGraphClient: {e}")
        return None
