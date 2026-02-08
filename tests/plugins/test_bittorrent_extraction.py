"""Tests for BitTorrent extraction pipeline and steps."""

import pytest

from haven_cli.plugins.builtin.bittorrent.sources.base import MagnetLink
from haven_cli.plugins.builtin.bittorrent.sources.extraction import (
    ExtractionContext,
    ExtractionPipeline,
    ForEachElement,
)
from haven_cli.plugins.builtin.bittorrent.sources.steps import (
    BuildMagnetLinkStep,
    ExtractAttributeStep,
    ExtractTextStep,
    FetchHtmlStep,
    RegexStep,
    SelectElementsStep,
    SetVariableStep,
)


class TestExtractionContext:
    """Tests for ExtractionContext."""
    
    def test_context_creation(self):
        """Test creating a context."""
        context = ExtractionContext(query="test")
        assert context.query == "test"
        assert context.raw_html == ""
        assert len(context.magnet_links) == 0
    
    def test_context_variables(self):
        """Test setting and getting variables."""
        context = ExtractionContext()
        context.set_variable("key", "value")
        assert context.get_variable("key") == "value"
        assert context.get_variable("missing", "default") == "default"
    
    def test_context_clone(self):
        """Test cloning a context."""
        context = ExtractionContext(query="test")
        context.set_variable("key", "value")
        
        cloned = context.clone(query="new")
        assert cloned.query == "new"
        assert cloned.get_variable("key") == "value"
        assert context.query == "test"


class TestSetVariableStep:
    """Tests for SetVariableStep."""
    
    @pytest.mark.asyncio
    async def test_set_variable(self):
        """Test setting a variable."""
        step = SetVariableStep(key="test_key", value="test_value")
        context = ExtractionContext()
        
        result = await step.execute(context)
        assert result.get_variable("test_key") == "test_value"


class TestBuildMagnetLinkStep:
    """Tests for BuildMagnetLinkStep."""
    
    @pytest.mark.asyncio
    async def test_build_magnet_link(self):
        """Test building a magnet link from data."""
        step = BuildMagnetLinkStep(source_name="test")
        context = ExtractionContext()
        context.current_data = {
            "infohash": "a" * 40,
            "uri": "magnet:?xt=urn:btih:" + "a" * 40,
            "title": "Test Torrent",
            "size": 1024 * 1024 * 1024,
            "seeders": 10,
            "leechers": 5,
            "category": "video",
        }
        
        result = await step.execute(context)
        assert len(result.magnet_links) == 1
        
        magnet = result.magnet_links[0]
        assert magnet.infohash == "a" * 40
        assert magnet.title == "Test Torrent"
        assert magnet.size == 1024 * 1024 * 1024
        assert magnet.seeders == 10
        assert magnet.leechers == 5
        assert magnet.category == "video"
        assert magnet.source_name == "test"
    
    @pytest.mark.asyncio
    async def test_build_magnet_link_missing_infohash(self):
        """Test building a magnet link without infohash."""
        step = BuildMagnetLinkStep()
        context = ExtractionContext()
        context.current_data = {"title": "Test"}
        
        result = await step.execute(context)
        assert len(result.magnet_links) == 0
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_build_magnet_link_auto_uri(self):
        """Test building a magnet link with auto-generated URI."""
        step = BuildMagnetLinkStep()
        context = ExtractionContext()
        context.current_data = {
            "infohash": "b" * 40,
            "title": "Test",
        }
        
        result = await step.execute(context)
        assert len(result.magnet_links) == 1
        assert result.magnet_links[0].uri == f"magnet:?xt=urn:btih:{'b' * 40}"


class TestRegexStep:
    """Tests for RegexStep."""
    
    @pytest.mark.asyncio
    async def test_regex_extract(self):
        """Test extracting with regex."""
        step = RegexStep(
            pattern=r"btih:([a-fA-F0-9]{40})",
            input_key="magnet_uri",
            output_key="infohash",
        )
        context = ExtractionContext()
        context.current_data = {
            "magnet_uri": "magnet:?xt=urn:btih:" + "c" * 40,
        }
        
        result = await step.execute(context)
        assert result.current_data["infohash"] == "c" * 40
    
    @pytest.mark.asyncio
    async def test_regex_no_match(self):
        """Test regex with no match."""
        step = RegexStep(
            pattern=r"btih:([a-fA-F0-9]{40})",
            input_key="text",
            output_key="infohash",
        )
        context = ExtractionContext()
        context.current_data = {"text": "no match here"}
        
        result = await step.execute(context)
        assert result.current_data["infohash"] is None


class TestExtractAttributeStep:
    """Tests for ExtractAttributeStep."""
    
    @pytest.mark.asyncio
    async def test_extract_attribute(self):
        """Test extracting an attribute."""
        from bs4 import Tag
        
        step = ExtractAttributeStep(attribute="href", output_key="url")
        context = ExtractionContext()
        
        # Create a mock element
        element = Tag(name="a")
        element["href"] = "https://example.com"
        context.current_element = element
        
        result = await step.execute(context)
        assert result.current_data["url"] == "https://example.com"
    
    @pytest.mark.asyncio
    async def test_extract_attribute_missing(self):
        """Test extracting a missing attribute."""
        from bs4 import Tag
        
        step = ExtractAttributeStep(attribute="href", output_key="url", default="default")
        context = ExtractionContext()
        context.current_element = Tag(name="a")
        
        result = await step.execute(context)
        assert result.current_data["url"] == "default"


class TestExtractTextStep:
    """Tests for ExtractTextStep."""
    
    @pytest.mark.asyncio
    async def test_extract_text(self):
        """Test extracting text from element."""
        from bs4 import Tag
        
        step = ExtractTextStep(output_key="title")
        context = ExtractionContext()
        
        element = Tag(name="div")
        element.string = "  Test Title  "
        context.current_element = element
        
        result = await step.execute(context)
        assert result.current_data["title"] == "Test Title"
    
    @pytest.mark.asyncio
    async def test_extract_text_no_strip(self):
        """Test extracting text without stripping."""
        from bs4 import Tag
        
        step = ExtractTextStep(output_key="title", strip=False)
        context = ExtractionContext()
        
        element = Tag(name="div")
        element.string = "  Test Title  "
        context.current_element = element
        
        result = await step.execute(context)
        assert result.current_data["title"] == "  Test Title  "


class TestMagnetLink:
    """Tests for MagnetLink dataclass."""
    
    def test_magnet_link_creation(self):
        """Test creating a magnet link."""
        magnet = MagnetLink(
            infohash="a" * 40,
            uri="magnet:?xt=urn:btih:" + "a" * 40,
            title="Test",
        )
        assert magnet.infohash == "a" * 40
        assert magnet.title == "Test"
    
    def test_magnet_link_validation(self):
        """Test magnet link validation."""
        with pytest.raises(ValueError, match="Invalid infohash length"):
            MagnetLink(infohash="short", uri="magnet:?xt=urn:btih:short")
        
        with pytest.raises(ValueError, match="Invalid infohash format"):
            MagnetLink(infohash="z" * 40, uri="magnet:?xt=urn:btih:" + "z" * 40)
    
    def test_magnet_link_from_uri(self):
        """Test creating magnet link from URI."""
        uri = f"magnet:?xt=urn:btih:{'a' * 40}&dn=Test+Title"
        magnet = MagnetLink.from_magnet_uri(uri)
        
        assert magnet.infohash == "a" * 40
        assert magnet.uri == uri
        assert magnet.title == "Test+Title"  # URL-encoded
    
    def test_magnet_link_to_dict(self):
        """Test converting magnet link to dict."""
        magnet = MagnetLink(
            infohash="a" * 40,
            uri="magnet:?xt=urn:btih:" + "a" * 40,
            title="Test",
        )
        data = magnet.to_dict()
        
        assert data["infohash"] == "a" * 40
        assert data["title"] == "Test"
        assert "discovered_at" in data


class TestExtractionPipeline:
    """Tests for ExtractionPipeline."""
    
    @pytest.mark.asyncio
    async def test_pipeline_execution(self):
        """Test executing a pipeline."""
        pipeline = ExtractionPipeline([
            SetVariableStep(key="test", value="value"),
            SetVariableStep(key="test2", value="value2"),
        ])
        
        context = await pipeline.execute()
        assert context.get_variable("test") == "value"
        assert context.get_variable("test2") == "value2"
    
    @pytest.mark.asyncio
    async def test_pipeline_extract(self):
        """Test pipeline extract convenience method."""
        pipeline = ExtractionPipeline([
            SetVariableStep(key="test", value="value"),
            BuildMagnetLinkStep(),
        ])
        
        # Set up data for magnet link
        context = ExtractionContext()
        context.current_data = {
            "infohash": "a" * 40,
            "uri": "magnet:?xt=urn:btih:" + "a" * 40,
        }
        
        magnets = await pipeline.extract(initial_context=context)
        assert len(magnets) == 1


class TestForEachElement:
    """Tests for ForEachElement."""
    
    @pytest.mark.asyncio
    async def test_for_each_element(self):
        """Test iterating over elements."""
        from bs4 import Tag
        
        # Create mock elements
        elements = []
        for i in range(3):
            element = Tag(name="div")
            element["data-id"] = str(i)
            elements.append(element)
        
        # Create step that extracts data-id
        step = ExtractAttributeStep(attribute="data-id", output_key="id")
        
        # Create for-each step
        for_each = ForEachElement(steps=[step])
        
        # Create context with elements
        context = ExtractionContext()
        context.elements = elements
        
        # Execute
        result = await for_each.execute(context)
        
        # Check that data was extracted for each element
        assert len(result.extracted_data) == 3
        assert result.extracted_data[0]["id"] == "0"
        assert result.extracted_data[1]["id"] == "1"
        assert result.extracted_data[2]["id"] == "2"
