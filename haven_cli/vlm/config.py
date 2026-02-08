"""VLM configuration management for Haven CLI.

This module provides configuration loading and management for VLM analysis,
matching the backend VLM configuration structure.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from haven_cli.config import get_config, PipelineConfig


@dataclass
class VLMEngineConfig:
    """Configuration for a VLM engine.
    
    Attributes:
        model_name: Specific model identifier (e.g., "zai-org/glm-4.6v-flash")
        api_key: API key for the service (optional, can be set per endpoint)
        timeout: Request timeout in seconds
        max_tokens: Maximum tokens in response
        max_concurrent: Maximum concurrent requests
    """
    
    model_name: str = "zai-org/glm-4.6v-flash"
    api_key: Optional[str] = None
    timeout: float = 120.0
    max_tokens: int = 4096
    max_concurrent: int = 5


@dataclass
class VLMProcessingConfig:
    """Configuration for VLM video processing.
    
    Attributes:
        enabled: Whether VLM analysis is enabled
        frame_count: Number of frames to sample for analysis
        frame_interval: Seconds between frame samples
        threshold: Confidence threshold for tag detection
        return_timestamps: Whether to extract timestamps
        return_confidence: Whether to return confidence scores
        save_to_file: Whether to save results to .AI.json file
    """
    
    enabled: bool = True
    frame_count: int = 20
    frame_interval: float = 2.0
    threshold: float = 0.5
    return_timestamps: bool = True
    return_confidence: bool = True
    save_to_file: bool = True


@dataclass
class VLMMultiplexerEndpoint:
    """Configuration for a multiplexer endpoint.
    
    Used for load balancing across multiple OpenAI-compatible VLM servers.
    
    Attributes:
        base_url: Endpoint URL (e.g., "http://localhost:1234/v1")
        api_key: API key for this endpoint
        name: Human-readable name
        weight: Load balancing weight
        max_concurrent: Maximum concurrent requests for this endpoint
        model_id: Model identifier to use for this endpoint
    """
    
    base_url: str
    name: str
    weight: int = 1
    max_concurrent: int = 5
    api_key: Optional[str] = None
    model_id: Optional[str] = None


@dataclass
class VLMMultiplexerConfig:
    """Configuration for VLM multiplexer (load balancing).
    
    Attributes:
        enabled: Whether multiplexer is enabled
        endpoints: List of endpoint configurations
        max_concurrent_requests: Global limit on concurrent requests
    """
    
    enabled: bool = False
    endpoints: List[VLMMultiplexerEndpoint] = field(default_factory=list)
    max_concurrent_requests: int = 10


@dataclass
class VLMConfig:
    """Complete VLM configuration.
    
    Combines engine, processing, and multiplexer configurations.
    Matches the gold standard backend's VLM configuration structure.
    """
    
    engine: VLMEngineConfig = field(default_factory=VLMEngineConfig)
    processing: VLMProcessingConfig = field(default_factory=VLMProcessingConfig)
    multiplexer: VLMMultiplexerConfig = field(default_factory=VLMMultiplexerConfig)
    
    # Additional settings
    cache_enabled: bool = True
    cache_dir: Optional[Path] = None
    
    # Analysis tags - list of tags to detect in videos
    analysis_tags: List[str] = field(default_factory=lambda: ["person", "car", "bicycle"])
    
    # Detected tag confidence threshold
    detected_tag_confidence: float = 0.99


def load_vlm_config() -> VLMConfig:
    """Load VLM configuration from Haven CLI config.
    
    This function translates Haven CLI's PipelineConfig settings into
    VLMConfig format, matching the gold standard backend configuration.
    
    Returns:
        VLMConfig instance with loaded settings
    """
    config = get_config()
    pipeline = config.pipeline
    
    # Parse analysis tags from comma-separated string
    analysis_tags = [tag.strip() for tag in pipeline.vlm_analysis_tags.split(',') if tag.strip()]
    
    # Build engine config
    engine_config = VLMEngineConfig(
        model_name=pipeline.vlm_model,
        api_key=pipeline.vlm_api_key,
        timeout=pipeline.vlm_timeout,
        max_tokens=pipeline.vlm_max_new_tokens,
        max_concurrent=pipeline.vlm_max_concurrent_requests,
    )
    
    # Build processing config
    processing_config = VLMProcessingConfig(
        enabled=pipeline.vlm_enabled,
        frame_count=20,
        frame_interval=pipeline.vlm_frame_interval,
        threshold=pipeline.vlm_threshold,
        return_timestamps=pipeline.vlm_return_timestamps,
        return_confidence=pipeline.vlm_return_confidence,
        save_to_file=True,
    )
    
    # Build multiplexer config
    multiplexer_endpoints = []
    if pipeline.vlm_multiplexer_endpoints:
        for ep_data in pipeline.vlm_multiplexer_endpoints:
            multiplexer_endpoints.append(VLMMultiplexerEndpoint(
                base_url=ep_data.get("base_url", ""),
                name=ep_data.get("name", "default"),
                weight=ep_data.get("weight", 1),
                max_concurrent=ep_data.get("max_concurrent", 5),
                api_key=ep_data.get("api_key"),
                model_id=ep_data.get("model_id", pipeline.vlm_model),
            ))
    
    multiplexer_config = VLMMultiplexerConfig(
        enabled=pipeline.vlm_multiplexer_enabled,
        endpoints=multiplexer_endpoints,
        max_concurrent_requests=pipeline.vlm_max_concurrent_requests,
    )
    
    # Build complete config
    vlm_config = VLMConfig(
        engine=engine_config,
        processing=processing_config,
        multiplexer=multiplexer_config,
        cache_enabled=True,
        cache_dir=Path(config.data_dir) / "vlm_cache" if config.data_dir else None,
        analysis_tags=analysis_tags,
        detected_tag_confidence=pipeline.vlm_detected_tag_confidence,
    )
    
    # Override with environment variables if present
    vlm_config = _apply_env_overrides(vlm_config)
    
    return vlm_config


def _apply_env_overrides(config: VLMConfig) -> VLMConfig:
    """Apply environment variable overrides to config.
    
    Args:
        config: Current configuration
        
    Returns:
        Updated configuration
    """
    # API key override
    if api_key := os.environ.get("VLM_API_KEY"):
        config.engine.api_key = api_key
    
    # Processing config overrides
    if frame_count := os.environ.get("VLM_FRAME_COUNT"):
        try:
            config.processing.frame_count = int(frame_count)
        except ValueError:
            pass
    
    if threshold := os.environ.get("VLM_THRESHOLD"):
        try:
            config.processing.threshold = float(threshold)
        except ValueError:
            pass
    
    if interval := os.environ.get("VLM_FRAME_INTERVAL"):
        try:
            config.processing.frame_interval = float(interval)
        except ValueError:
            pass
    
    # Enable/disable overrides
    if enabled := os.environ.get("VLM_ENABLED"):
        config.processing.enabled = enabled.lower() in ("true", "1", "yes")
    
    # Analysis tags override (comma-separated)
    if analysis_tags := os.environ.get("VLM_ANALYSIS_TAGS"):
        config.analysis_tags = [tag.strip() for tag in analysis_tags.split(',') if tag.strip()]
    
    # Detected tag confidence override
    if tag_confidence := os.environ.get("VLM_DETECTED_TAG_CONFIDENCE"):
        try:
            config.detected_tag_confidence = float(tag_confidence)
        except ValueError:
            pass
    
    # Multiplexer overrides
    if multiplexer_enabled := os.environ.get("VLM_MULTIPLEXER_ENABLED"):
        config.multiplexer.enabled = multiplexer_enabled.lower() in ("true", "1", "yes")
    
    if max_concurrent := os.environ.get("VLM_MAX_CONCURRENT_REQUESTS"):
        try:
            config.multiplexer.max_concurrent_requests = int(max_concurrent)
            config.engine.max_concurrent = int(max_concurrent)
        except ValueError:
            pass
    
    return config


def get_engine_config(config: Optional[VLMConfig] = None) -> VLMEngineConfig:
    """Get the engine configuration.
    
    Args:
        config: Optional VLMConfig (loads from global if not provided)
        
    Returns:
        VLMEngineConfig instance
    """
    if config is None:
        config = load_vlm_config()
    return config.engine


def get_processing_params(config: Optional[VLMConfig] = None) -> Dict[str, Any]:
    """Get processing parameters as a dictionary.
    
    Matches the backend's get_vlm_processing_params() function.
    
    Args:
        config: Optional VLMConfig (loads from global if not provided)
        
    Returns:
        Dictionary of processing parameters
    """
    if config is None:
        config = load_vlm_config()
    
    return {
        "enabled": config.processing.enabled,
        "frame_count": config.processing.frame_count,
        "frame_interval": config.processing.frame_interval,
        "threshold": config.processing.threshold,
        "return_timestamps": config.processing.return_timestamps,
        "return_confidence": config.processing.return_confidence,
        "save_to_file": config.processing.save_to_file,
        "analysis_tags": config.analysis_tags,
        "detected_tag_confidence": config.detected_tag_confidence,
        "vr_video": False,
    }


def create_analysis_config(config: Optional[VLMConfig] = None) -> "AnalysisConfig":
    """Create an AnalysisConfig from VLMConfig.
    
    Args:
        config: Optional VLMConfig (loads from global if not provided)
        
    Returns:
        AnalysisConfig instance for use with VLM engines
    """
    from haven_cli.vlm.engine import AnalysisConfig
    
    if config is None:
        config = load_vlm_config()
    
    return AnalysisConfig(
        frame_count=config.processing.frame_count,
        frame_interval=config.processing.frame_interval,
        threshold=config.processing.threshold,
        return_timestamps=config.processing.return_timestamps,
        return_confidence=config.processing.return_confidence,
        max_tokens=config.engine.max_tokens,
        timeout=config.engine.timeout,
    )


def save_multiplexer_config(endpoints: List[Dict[str, Any]], config_path: Optional[Path] = None) -> None:
    """Save multiplexer endpoint configuration.
    
    Args:
        endpoints: List of endpoint dictionaries
        config_path: Path to save configuration (default: data_dir/multiplexer.json)
    """
    config = get_config()
    
    if config_path is None:
        config_path = Path(config.data_dir) / "vlm_multiplexer.json"
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, "w") as f:
        json.dump({"endpoints": endpoints}, f, indent=2)


def load_multiplexer_config(config_path: Optional[Path] = None) -> List[VLMMultiplexerEndpoint]:
    """Load multiplexer endpoint configuration.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        List of multiplexer endpoints
    """
    config = get_config()
    
    if config_path is None:
        config_path = Path(config.data_dir) / "vlm_multiplexer.json"
    
    if not config_path.exists():
        return []
    
    try:
        with open(config_path) as f:
            data = json.load(f)
        
        endpoints = []
        for ep_data in data.get("endpoints", []):
            endpoints.append(VLMMultiplexerEndpoint(**ep_data))
        
        return endpoints
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Warning: Failed to load multiplexer config: {e}")
        return []


def get_example_multiplexer_config() -> str:
    """Get example multiplexer configuration as JSON string.
    
    Returns:
        Example configuration JSON
    """
    example = {
        "enabled": True,
        "max_concurrent_requests": 25,
        "endpoints": [
            {
                "base_url": "http://primary-server:1234/v1",
                "name": "primary-server",
                "weight": 8,
                "max_concurrent": 10,
                "model_id": "zai-org/glm-4.6v-flash",
            },
            {
                "base_url": "http://secondary-server:1234/v1",
                "name": "secondary-server",
                "weight": 1,
                "max_concurrent": 8,
                "model_id": "zai-org/glm-4.6v-flash",
            },
            {
                "base_url": "http://fallback-server:1234/v1",
                "name": "fallback-server",
                "weight": 1,
                "max_concurrent": 2,
                "model_id": "zai-org/glm-4.6v-flash",
            },
        ],
    }
    
    return json.dumps(example, indent=2)


def validate_vlm_config(config: Optional[VLMConfig] = None) -> List[str]:
    """Validate VLM configuration and return list of issues.
    
    Args:
        config: VLMConfig to validate (loads from global if not provided)
        
    Returns:
        List of validation error messages (empty if valid)
    """
    if config is None:
        config = load_vlm_config()
    
    errors: List[str] = []
    
    # Validate processing parameters
    if config.processing.frame_count < 1:
        errors.append("frame_count must be at least 1")
    
    if config.processing.frame_count > 100:
        errors.append("frame_count seems high (>100), this may be slow/expensive")
    
    if not 0 <= config.processing.threshold <= 1:
        errors.append("threshold must be between 0 and 1")
    
    # Validate timeout
    if config.engine.timeout < 1:
        errors.append("timeout must be at least 1 second")
    
    # Validate detected tag confidence
    if not 0 <= config.detected_tag_confidence <= 1:
        errors.append("detected_tag_confidence must be between 0 and 1")
    
    # Validate analysis tags
    if not config.analysis_tags:
        errors.append("analysis_tags cannot be empty")
    
    # Validate multiplexer endpoints if enabled
    if config.multiplexer.enabled:
        if not config.multiplexer.endpoints:
            errors.append("Multiplexer enabled but no endpoints configured")
        
        for i, ep in enumerate(config.multiplexer.endpoints):
            if not ep.base_url:
                errors.append(f"Endpoint {i}: base_url is required")
            if ep.weight < 1:
                errors.append(f"Endpoint {i}: weight must be a positive integer")
            if ep.max_concurrent < 1:
                errors.append(f"Endpoint {i}: max_concurrent must be a positive integer")
    
    return errors
