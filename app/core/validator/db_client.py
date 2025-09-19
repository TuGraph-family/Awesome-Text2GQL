from abc import ABC, abstractmethod


class DB_Client(ABC):
    @abstractmethod
    def create_client(db_client_params: dict):
        """create a new DB_Client instance"""

class result():
    # core/
    pass