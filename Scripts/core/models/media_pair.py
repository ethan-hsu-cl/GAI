"""Media pair data model."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

@dataclass
class MediaPair:
    """Universal media pair for all API types."""
    source_file: str
    source_path: Path
    api_type: str
    
    # Generated content
    generated_paths: List[Path] = field(default_factory=list)
    reference_paths: List[Path] = field(default_factory=list)
    
    # API-specific fields
    effect_name: str = ""
    category: str = ""
    prompt: str = ""
    
    # Video-specific (for Runway)
    source_video_path: Optional[Path] = None
    
    # Metadata
    metadata: Dict = field(default_factory=dict)
    ref_metadata: Dict = field(default_factory=dict)
