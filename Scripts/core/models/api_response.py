"""API response data model."""
from dataclasses import dataclass
from typing import Any, Optional, Dict, List

@dataclass
class APIResponse:
    """Standard API response structure."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
