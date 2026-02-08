"""VLM Engine compatibility layer for backend gold standard.

This module provides a backend-compatible VLMEngine interface that matches
the gold standard backend's vlm_engine package structure.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from haven_cli.vlm.engine import (
    VLMEngine as BaseVLMEngine,
    create_vlm_engine as create_base_engine,
    AnalysisConfig,
)
from haven_cli.vlm.config import (
    VLMConfig,
    load_vlm_config,
    get_engine_config,
    create_analysis_config,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Model configuration matching backend's ModelConfig."""
    type: str = "vlm_model"
    model_id: str = "zai-org/glm-4.6v-flash"
    api_base_url: Optional[str] = None
    tag_list: List[str] = field(default_factory=list)
    max_new_tokens: int = 128
    request_timeout: float = 70.0
    vlm_detected_tag_confidence: float = 0.99
    # Multiplexer configuration
    multiplexer_endpoints: Optional[List[Dict[str, Any]]] = None
    use_multiplexer: bool = False
    max_batch_size: int = 5
    instance_count: int = 5


@dataclass
class PipelineConfig:
    """Pipeline configuration matching backend's PipelineConfig."""
    inputs: List[str] = field(default_factory=lambda: [
        "video_path", "return_timestamps", "time_interval", 
        "threshold", "return_confidence", "vr_video"
    ])
    output: str = "results"
    short_name: str = "video_analysis"
    version: float = 1.0


@dataclass
class PipelineModelConfig:
    """Pipeline model configuration."""
    name: str = "vlm_analysis"
    inputs: List[str] = field(default_factory=lambda: ["video_path"])
    outputs: str = "tags"


@dataclass
class EngineConfig:
    """Engine configuration matching backend's EngineConfig.
    
    This is the primary configuration object used to initialize VLMEngine.
    """
    loglevel: str = "INFO"
    pipelines: Dict[str, PipelineConfig] = field(default_factory=lambda: {
        "video_pipeline_dynamic": PipelineConfig()
    })
    models: Dict[str, ModelConfig] = field(default_factory=lambda: {
        "vlm_nsfw_model": ModelConfig()
    })
    category_config: Dict[str, Any] = field(default_factory=dict)
    active_ai_models: List[str] = field(default_factory=lambda: ["vlm_nsfw_model"])


class VLMEngine:
    """Backend-compatible VLM Engine.
    
    This class provides the same interface as the backend's vlm_engine.VLMEngine
    but uses the haven-cli's underlying engine implementation.
    
    Example:
        >>> from haven_cli.vlm.engine_compat import VLMEngine, EngineConfig
        >>> config = EngineConfig()
        >>> engine = VLMEngine(config=config)
        >>> await engine.initialize()
        >>> results = await engine.process_video("/path/to/video.mp4")
    """
    
    def __init__(self, config: EngineConfig):
        """Initialize the VLMEngine with the provided configuration.
        
        Args:
            config: EngineConfig object containing the configuration
        """
        self.config = config
        self._engine: Optional[BaseVLMEngine] = None
        self._vlm_config: Optional[VLMConfig] = None
        self._initialized = False
        
        # Get the first active model config
        self._model_config = None
        if config.active_ai_models and config.models:
            model_name = config.active_ai_models[0]
            self._model_config = config.models.get(model_name, ModelConfig())
    
    async def initialize(self) -> None:
        """Initialize the engine.
        
        Loads the VLM configuration and creates the underlying engine.
        """
        if self._initialized:
            return
        
        # Load VLM config from haven-cli config
        self._vlm_config = load_vlm_config()
        
        # Get engine and analysis configuration
        engine_config = get_engine_config(self._vlm_config)
        analysis_config = create_analysis_config(self._vlm_config)
        
        # Get base_url from multiplexer endpoints
        base_url = None
        if (self._vlm_config.multiplexer.enabled and 
            self._vlm_config.multiplexer.endpoints):
            base_url = self._vlm_config.multiplexer.endpoints[0].base_url
            logger.info(f"Using multiplexer endpoint: {base_url}")
        
        # Override with model config if available
        if self._model_config and self._model_config.api_base_url:
            base_url = self._model_config.api_base_url
        
        # Create the underlying engine
        self._engine = create_base_engine(
            model=engine_config.model_name,
            api_key=engine_config.api_key,
            base_url=base_url,
            config=analysis_config,
        )
        
        # Initialize the underlying engine
        if self._engine:
            await self._engine.initialize()
        
        self._initialized = True
        logger.info("VLMEngine initialized")
    
    async def process_video(
        self,
        video_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Process a video and return tagging information.
        
        Args:
            video_path: Path to the video file
            progress_callback: Optional callback for progress updates (progress 0-100)
            **kwargs: Additional processing parameters
                - frame_interval: Seconds between frame samples
                - threshold: Confidence threshold for tag detection
                - return_timestamps: Whether to include timestamps
                - return_confidence: Whether to include confidence scores
                - vr_video: Whether video is VR format
                
        Returns:
            Dictionary containing tagging information
        """
        if not self._initialized:
            raise RuntimeError("VLMEngine not initialized. Call initialize() first.")
        
        if not self._engine:
            raise RuntimeError("Engine not created")
        
        # Process video using underlying engine
        from haven_cli.vlm.processor import VLMProcessor
        
        # Create a temporary processor with our engine
        processor = VLMProcessor(engine=self._engine, config=self._vlm_config)
        
        # Get processing parameters from config or kwargs
        frame_interval = kwargs.get(
            "frame_interval", 
            self._vlm_config.processing.frame_interval if self._vlm_config else 2.0
        )
        threshold = kwargs.get(
            "threshold",
            self._vlm_config.processing.threshold if self._vlm_config else 0.5
        )
        
        # Process the video
        results = await processor.process_video(
            video_path=video_path,
            progress_callback=progress_callback,
            threshold=threshold,
        )
        
        return results
    
    async def close(self) -> None:
        """Close the engine and release resources."""
        if self._engine and hasattr(self._engine, 'close'):
            await self._engine.close()
        self._initialized = False


def create_engine_config(
    model_name: str = "zai-org/glm-4.6v-flash",
    api_base_url: Optional[str] = None,
    tag_list: Optional[List[str]] = None,
    use_multiplexer: bool = True,
    multiplexer_endpoints: Optional[List[Dict[str, Any]]] = None,
) -> EngineConfig:
    """Create an EngineConfig matching the backend's configuration.
    
    Args:
        model_name: VLM model identifier
        api_base_url: Base URL for the API
        tag_list: List of tags to detect
        use_multiplexer: Whether to use multiplexer
        multiplexer_endpoints: List of multiplexer endpoint configurations
        
    Returns:
        Configured EngineConfig instance
    """
    model_config = ModelConfig(
        model_id=model_name,
        api_base_url=api_base_url,
        tag_list=tag_list or [],
        use_multiplexer=use_multiplexer,
        multiplexer_endpoints=multiplexer_endpoints,
    )
    
    return EngineConfig(
        models={"vlm_nsfw_model": model_config},
        active_ai_models=["vlm_nsfw_model"],
    )
