"""Abstract base class for report generators."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List
from ..models.media_pair import MediaPair

class BaseReporter(ABC):
    """Abstract base class for report generators."""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.media_pairs = []
        
    @abstractmethod
    def collect_media_pairs(self) -> List[MediaPair]:
        """Collect media pairs for report generation."""
        pass
        
    @abstractmethod
    def generate_report(self, output_path: Path) -> bool:
        """Generate the report. Returns True if successful."""
        pass
