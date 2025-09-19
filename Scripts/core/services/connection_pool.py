"""Connection pooling for API clients."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict
import logging

class ConnectionPool:
    """Manages HTTP connection pooling for API clients."""
    
    _sessions: Dict[str, requests.Session] = {}
    
    @classmethod
    def get_session(cls, endpoint: str) -> requests.Session:
        """Get or create a session for the given endpoint."""
        if endpoint not in cls._sessions:
            session = requests.Session()
            
            # Configure retry strategy
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=10,
                pool_maxsize=20
            )
            
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            cls._sessions[endpoint] = session
            
        return cls._sessions[endpoint]
    
    @classmethod
    def close_all(cls):
        """Close all sessions."""
        for session in cls._sessions.values():
            session.close()
        cls._sessions.clear()
