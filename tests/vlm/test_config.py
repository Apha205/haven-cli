"""Tests for VLM configuration."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from haven_cli.vlm.config import (
    VLMConfig,
    VLMEngineConfig,
    VLMProcessingConfig,
    VLMMultiplexerConfig,
    VLMMultiplexerEndpoint,
    create_analysis_config,
    get_engine_config,
    get_processing_params,
    load_vlm_config,
    validate_vlm_config,
    save_multiplexer_config,
    load_multiplexer_config,
    get_example_multiplexer_config,
    _apply_env_overrides,
)


class TestVLMEngineConfig:
    """Tests for VLMEngineConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = VLMEngineConfig()
        
        assert config.model_name == "zai-org/glm-4.6v-flash"
        assert config.api_key is None
        assert config.timeout == 120.0
        assert config.max_tokens == 4096
        assert config.max_concurrent == 5
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = VLMEngineConfig(
            model_name="custom-model",
            api_key="test-key",
            timeout=60.0,
            max_tokens=2048,
        )
        
        assert config.model_name == "custom-model"
        assert config.api_key == "test-key"
        assert config.timeout == 60.0
        assert config.max_tokens == 2048


class TestVLMProcessingConfig:
    """Tests for VLMProcessingConfig dataclass."""
    
    def test_default_values(self):
        """Test default processing configuration."""
        config = VLMProcessingConfig()
        
        assert config.enabled is True
        assert config.frame_count == 20
        assert config.frame_interval == 2.0
        assert config.threshold == 0.5
        assert config.return_timestamps is True
        assert config.return_confidence is True
        assert config.save_to_file is True


class TestVLMMultiplexerEndpoint:
    """Tests for VLMMultiplexerEndpoint dataclass."""
    
    def test_default_values(self):
        """Test default endpoint configuration."""
        config = VLMMultiplexerEndpoint(
            base_url="http://localhost:8000/v1",
            name="default",
        )
        
        assert config.base_url == "http://localhost:8000/v1"
        assert config.name == "default"
        assert config.weight == 1
        assert config.max_concurrent == 5
        assert config.api_key is None


class TestApplyEnvOverrides:
    """Tests for environment variable overrides."""
    
    def test_vlm_api_key_override(self):
        """Test VLM_API_KEY environment variable."""
        config = VLMConfig()
        
        with patch.dict(os.environ, {"VLM_API_KEY": "test-vlm-key"}):
            result = _apply_env_overrides(config)
        
        assert result.engine.api_key == "test-vlm-key"
    
    def test_frame_count_override(self):
        """Test VLM_FRAME_COUNT environment variable."""
        config = VLMConfig()
        
        with patch.dict(os.environ, {"VLM_FRAME_COUNT": "15"}):
            result = _apply_env_overrides(config)
        
        assert result.processing.frame_count == 15
    
    def test_threshold_override(self):
        """Test VLM_THRESHOLD environment variable."""
        config = VLMConfig()
        
        with patch.dict(os.environ, {"VLM_THRESHOLD": "0.7"}):
            result = _apply_env_overrides(config)
        
        assert result.processing.threshold == 0.7
    
    def test_enabled_override(self):
        """Test VLM_ENABLED environment variable."""
        config = VLMConfig()
        config.processing.enabled = True
        
        with patch.dict(os.environ, {"VLM_ENABLED": "false"}):
            result = _apply_env_overrides(config)
        
        assert result.processing.enabled is False
    
    def test_analysis_tags_override(self):
        """Test VLM_ANALYSIS_TAGS environment variable."""
        config = VLMConfig()
        
        with patch.dict(os.environ, {"VLM_ANALYSIS_TAGS": "cat,dog,bird"}):
            result = _apply_env_overrides(config)
        
        assert result.analysis_tags == ["cat", "dog", "bird"]
    
    def test_detected_tag_confidence_override(self):
        """Test VLM_DETECTED_TAG_CONFIDENCE environment variable."""
        config = VLMConfig()
        
        with patch.dict(os.environ, {"VLM_DETECTED_TAG_CONFIDENCE": "0.95"}):
            result = _apply_env_overrides(config)
        
        assert result.detected_tag_confidence == 0.95
    
    def test_multiplexer_enabled_override(self):
        """Test VLM_MULTIPLEXER_ENABLED environment variable."""
        config = VLMConfig()
        config.multiplexer.enabled = False
        
        with patch.dict(os.environ, {"VLM_MULTIPLEXER_ENABLED": "true"}):
            result = _apply_env_overrides(config)
        
        assert result.multiplexer.enabled is True
    
    def test_max_concurrent_requests_override(self):
        """Test VLM_MAX_CONCURRENT_REQUESTS environment variable."""
        config = VLMConfig()
        
        with patch.dict(os.environ, {"VLM_MAX_CONCURRENT_REQUESTS": "25"}):
            result = _apply_env_overrides(config)
        
        assert result.multiplexer.max_concurrent_requests == 25
        assert result.engine.max_concurrent == 25


class TestLoadVlmConfig:
    """Tests for load_vlm_config function."""
    
    def test_load_config(self):
        """Test loading configuration."""
        mock_pipeline_config = MagicMock()
        mock_pipeline_config.vlm_enabled = True
        mock_pipeline_config.vlm_model = "gpt-4-vision-preview"
        mock_pipeline_config.vlm_api_key = "test-key"
        mock_pipeline_config.vlm_timeout = 120.0
        mock_pipeline_config.vlm_frame_interval = 2.0
        mock_pipeline_config.vlm_threshold = 0.5
        mock_pipeline_config.vlm_return_timestamps = True
        mock_pipeline_config.vlm_return_confidence = True
        mock_pipeline_config.vlm_max_new_tokens = 128
        mock_pipeline_config.vlm_detected_tag_confidence = 0.99
        mock_pipeline_config.vlm_analysis_tags = "person,car,bicycle"
        mock_pipeline_config.vlm_multiplexer_enabled = True
        mock_pipeline_config.vlm_multiplexer_endpoints = [
            {"base_url": "http://localhost:1234/v1", "name": "local", "weight": 1, "max_concurrent": 5}
        ]
        mock_pipeline_config.vlm_max_concurrent_requests = 15
        
        mock_haven_config = MagicMock()
        mock_haven_config.pipeline = mock_pipeline_config
        mock_haven_config.data_dir = "/tmp/haven"
        
        with patch("haven_cli.vlm.config.get_config", return_value=mock_haven_config):
            config = load_vlm_config()
        
        assert config.processing.enabled is True
        assert config.engine.model_name == "gpt-4-vision-preview"
        assert config.engine.api_key == "test-key"
        assert config.multiplexer.enabled is True
        assert len(config.multiplexer.endpoints) == 1
        assert config.analysis_tags == ["person", "car", "bicycle"]


class TestGetEngineConfig:
    """Tests for get_engine_config function."""
    
    def test_get_engine_config(self):
        """Test getting engine configuration."""
        config = VLMConfig()
        config.engine.model_name = "custom-model"
        
        result = get_engine_config(config)
        
        assert result.model_name == "custom-model"
    
    def test_get_engine_config_from_global(self):
        """Test getting engine config from global."""
        mock_pipeline_config = MagicMock()
        mock_pipeline_config.vlm_model = "gpt-4o"
        mock_pipeline_config.vlm_api_key = "key"
        mock_pipeline_config.vlm_timeout = 120.0
        mock_pipeline_config.vlm_frame_interval = 2.0
        mock_pipeline_config.vlm_threshold = 0.5
        mock_pipeline_config.vlm_return_timestamps = True
        mock_pipeline_config.vlm_return_confidence = True
        mock_pipeline_config.vlm_max_new_tokens = 128
        mock_pipeline_config.vlm_detected_tag_confidence = 0.99
        mock_pipeline_config.vlm_analysis_tags = "person,car"
        mock_pipeline_config.vlm_multiplexer_enabled = False
        mock_pipeline_config.vlm_multiplexer_endpoints = []
        mock_pipeline_config.vlm_max_concurrent_requests = 10
        
        mock_haven_config = MagicMock()
        mock_haven_config.pipeline = mock_pipeline_config
        mock_haven_config.data_dir = "/tmp/haven"
        
        with patch("haven_cli.vlm.config.get_config", return_value=mock_haven_config):
            result = get_engine_config()
        
        assert result.model_name == "gpt-4o"


class TestGetProcessingParams:
    """Tests for get_processing_params function."""
    
    def test_get_params(self):
        """Test getting processing parameters."""
        config = VLMConfig()
        config.processing.frame_count = 15
        config.processing.threshold = 0.7
        
        result = get_processing_params(config)
        
        assert result["frame_count"] == 15
        assert result["threshold"] == 0.7
        assert "enabled" in result
        assert "return_timestamps" in result


class TestCreateAnalysisConfig:
    """Tests for create_analysis_config function."""
    
    def test_create_config(self):
        """Test creating AnalysisConfig from VLMConfig."""
        config = VLMConfig()
        config.processing.frame_count = 25
        config.processing.threshold = 0.6
        config.engine.max_tokens = 2048
        
        result = create_analysis_config(config)
        
        assert result.frame_count == 25
        assert result.threshold == 0.6
        assert result.max_tokens == 2048


class TestValidateVlmConfig:
    """Tests for validate_vlm_config function."""
    
    def test_valid_config(self):
        """Test validation of valid configuration."""
        config = VLMConfig()
        
        errors = validate_vlm_config(config)
        
        assert errors == []
    
    def test_invalid_frame_count(self):
        """Test validation of invalid frame count."""
        config = VLMConfig()
        config.processing.frame_count = 0
        
        errors = validate_vlm_config(config)
        
        assert any("frame_count" in e for e in errors)
    
    def test_high_frame_count_warning(self):
        """Test warning for high frame count."""
        config = VLMConfig()
        config.processing.frame_count = 150
        
        errors = validate_vlm_config(config)
        
        assert any("frame_count" in e.lower() for e in errors)
    
    def test_invalid_threshold(self):
        """Test validation of invalid threshold."""
        config = VLMConfig()
        config.processing.threshold = 1.5
        
        errors = validate_vlm_config(config)
        
        assert any("threshold" in e for e in errors)
    
    def test_invalid_timeout(self):
        """Test validation of invalid timeout."""
        config = VLMConfig()
        config.engine.timeout = 0
        
        errors = validate_vlm_config(config)
        
        assert any("timeout" in e for e in errors)
    
    def test_invalid_detected_tag_confidence(self):
        """Test validation of invalid detected_tag_confidence."""
        config = VLMConfig()
        config.detected_tag_confidence = 1.5
        
        errors = validate_vlm_config(config)
        
        assert any("detected_tag_confidence" in e for e in errors)
    
    def test_empty_analysis_tags(self):
        """Test validation with empty analysis tags."""
        config = VLMConfig()
        config.analysis_tags = []
        
        errors = validate_vlm_config(config)
        
        assert any("analysis_tags" in e for e in errors)
    
    def test_multiplexer_no_endpoints(self):
        """Test validation of multiplexer without endpoints."""
        config = VLMConfig()
        config.multiplexer.enabled = True
        config.multiplexer.endpoints = []
        
        errors = validate_vlm_config(config)
        
        assert any("endpoints" in e for e in errors)
    
    def test_multiplexer_invalid_endpoint_weight(self):
        """Test validation of endpoint with invalid weight."""
        config = VLMConfig()
        config.multiplexer.enabled = True
        config.multiplexer.endpoints = [
            VLMMultiplexerEndpoint(base_url="http://test/v1", name="test", weight=0)
        ]
        
        errors = validate_vlm_config(config)
        
        assert any("weight" in e for e in errors)
    
    def test_multiplexer_invalid_endpoint_max_concurrent(self):
        """Test validation of endpoint with invalid max_concurrent."""
        config = VLMConfig()
        config.multiplexer.enabled = True
        config.multiplexer.endpoints = [
            VLMMultiplexerEndpoint(base_url="http://test/v1", name="test", max_concurrent=0)
        ]
        
        errors = validate_vlm_config(config)
        
        assert any("max_concurrent" in e for e in errors)
    
    def test_multiplexer_missing_base_url(self):
        """Test validation of endpoint without base_url."""
        config = VLMConfig()
        config.multiplexer.enabled = True
        config.multiplexer.endpoints = [
            VLMMultiplexerEndpoint(base_url="", name="test")
        ]
        
        errors = validate_vlm_config(config)
        
        assert any("base_url" in e for e in errors)


class TestMultiplexerConfig:
    """Tests for multiplexer configuration functions."""
    
    def test_save_and_load_multiplexer_config(self, tmp_path):
        """Test saving and loading multiplexer configuration."""
        endpoints = [
            {
                "base_url": "http://server1:8000/v1",
                "name": "server1",
                "weight": 2,
                "max_concurrent": 5,
            },
            {
                "base_url": "http://server2:8000/v1",
                "name": "server2",
                "weight": 1,
                "max_concurrent": 3,
            },
        ]
        
        config_path = tmp_path / "multiplexer.json"
        
        with patch("haven_cli.vlm.config.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.data_dir = tmp_path
            mock_get_config.return_value = mock_config
            
            save_multiplexer_config(endpoints, config_path)
        
        assert config_path.exists()
        
        with patch("haven_cli.vlm.config.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.data_dir = tmp_path
            mock_get_config.return_value = mock_config
            
            loaded = load_multiplexer_config(config_path)
        
        assert len(loaded) == 2
        assert loaded[0].name == "server1"
        assert loaded[1].weight == 1
    
    def test_load_nonexistent_config(self, tmp_path):
        """Test loading non-existent configuration."""
        config_path = tmp_path / "nonexistent.json"
        
        with patch("haven_cli.vlm.config.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.data_dir = tmp_path
            mock_get_config.return_value = mock_config
            
            loaded = load_multiplexer_config(config_path)
        
        assert loaded == []
    
    def test_load_invalid_config(self, tmp_path):
        """Test loading invalid configuration file."""
        config_path = tmp_path / "invalid.json"
        config_path.write_text("not valid json")
        
        with patch("haven_cli.vlm.config.get_config") as mock_get_config:
            mock_config = MagicMock()
            mock_config.data_dir = tmp_path
            mock_get_config.return_value = mock_config
            
            loaded = load_multiplexer_config(config_path)
        
        assert loaded == []
    
    def test_get_example_multiplexer_config(self):
        """Test getting example multiplexer configuration."""
        example = get_example_multiplexer_config()
        
        # Should be valid JSON
        parsed = json.loads(example)
        
        assert parsed["enabled"] is True
        assert "endpoints" in parsed
        assert len(parsed["endpoints"]) == 3
