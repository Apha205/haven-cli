"""Cleanup step - Remove local files after successful pipeline completion.

This step cleans up local files after a video has been successfully processed,
encrypted, uploaded to Filecoin, and synced to Arkiv. It removes:
1. The original video file
2. The encrypted video file (if encryption was enabled)
3. The encryption metadata file (if encryption was enabled)

The step is conditional and only runs when cleanup_enabled option is set to True.
Files are only deleted if the previous steps (upload and optionally sync) succeeded.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from haven_cli.pipeline.context import PipelineContext
from haven_cli.pipeline.events import EventType
from haven_cli.pipeline.results import StepError, StepResult
from haven_cli.pipeline.step import ConditionalStep

logger = logging.getLogger(__name__)


class CleanupStep(ConditionalStep):
    """Pipeline step for cleaning up local files after successful processing.
    
    This step removes local files once they have been successfully:
    - Encrypted (if enabled)
    - Uploaded to Filecoin
    - Synced to Arkiv (if enabled)
    
    Files are only deleted if the pipeline has successfully completed
    the upload step. This ensures data is safely stored on Filecoin
    before local copies are removed.
    
    The step is conditional and can be enabled via the cleanup_enabled option.
    
    Emits:
        - CLEANUP_STARTED event when starting
        - CLEANUP_COMPLETE event on success
        - CLEANUP_FAILED event if cleanup fails
    
    Output data:
        - files_deleted: List of files that were deleted
        - files_missing: List of files that were already missing
        - bytes_freed: Total bytes freed by cleanup
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the cleanup step.
        
        Args:
            config: Step configuration (passed to base class)
        """
        super().__init__(config=config)
        self._files_deleted: List[str] = []
        self._files_missing: List[str] = []
        self._bytes_freed: int = 0
    
    @property
    def name(self) -> str:
        """Step identifier."""
        return "cleanup"
    
    @property
    def enabled_option(self) -> str:
        """Context option that enables this step."""
        return "cleanup_enabled"
    
    @property
    def default_enabled(self) -> bool:
        """Cleanup is disabled by default for safety."""
        return False
    
    async def should_skip(self, context: PipelineContext) -> bool:
        """Skip cleanup if upload didn't succeed or cleanup not enabled.
        
        Args:
            context: The pipeline context
            
        Returns:
            True if cleanup should be skipped
        """
        # Check if cleanup is enabled - check context.options first (CLI flags), 
        # then fall back to step config (from config file)
        enabled = context.options.get(
            self.enabled_option, 
            self._config.get(self.enabled_option, self.default_enabled)
        )
        if not enabled:
            self._skip_reason = "cleanup_enabled is disabled"
            return True
        
        # Skip if upload didn't succeed - we need the file on Filecoin first
        if context.upload_result is None or not context.upload_result.root_cid:
            self._skip_reason = "upload did not complete successfully"
            return True
        
        return False
    
    async def _get_skip_reason(self, context: PipelineContext) -> str:
        """Get the reason for skipping this step."""
        return getattr(self, '_skip_reason', f"{self.enabled_option} is disabled")
    
    async def process(self, context: PipelineContext) -> StepResult:
        """Process cleanup of local files.
        
        Args:
            context: Pipeline context with file paths
            
        Returns:
            StepResult with cleanup details
        """
        self._files_deleted = []
        self._files_missing = []
        self._bytes_freed = 0
        
        # Emit cleanup started event
        await self._emit_event(EventType.CLEANUP_STARTED, context, {
            "video_path": context.video_path,
        })
        
        try:
            # Collect all files to clean up
            files_to_cleanup = self._get_files_to_cleanup(context)
            
            logger.info(f"Starting cleanup for {len(files_to_cleanup)} files")
            
            # Delete each file
            for file_path in files_to_cleanup:
                await self._delete_file(file_path)
            
            # Log summary
            logger.info(
                f"Cleanup complete: {len(self._files_deleted)} files deleted, "
                f"{len(self._files_missing)} files already missing, "
                f"{self._bytes_freed} bytes freed"
            )
            
            # Emit cleanup complete event
            await self._emit_event(EventType.CLEANUP_COMPLETE, context, {
                "video_path": context.video_path,
                "files_deleted": self._files_deleted,
                "files_missing": self._files_missing,
                "bytes_freed": self._bytes_freed,
            })
            
            return StepResult.ok(
                self.name,
                files_deleted=self._files_deleted,
                files_missing=self._files_missing,
                bytes_freed=self._bytes_freed,
                files_count=len(files_to_cleanup),
            )
            
        except Exception as e:
            error_msg = f"Cleanup failed: {e}"
            logger.error(error_msg)
            
            # Emit cleanup failed event
            await self._emit_event(EventType.CLEANUP_FAILED, context, {
                "video_path": context.video_path,
                "error": error_msg,
                "files_deleted_before_error": self._files_deleted,
            })
            
            # Cleanup errors are non-fatal - log but don't fail the pipeline
            # We've already successfully uploaded the file
            return StepResult.ok(
                self.name,
                files_deleted=self._files_deleted,
                files_missing=self._files_missing,
                bytes_freed=self._bytes_freed,
                warning=error_msg,
                partial=True,
            )
    
    def _get_files_to_cleanup(self, context: PipelineContext) -> List[str]:
        """Get list of files to clean up.
        
        Args:
            context: Pipeline context with file paths
            
        Returns:
            List of file paths to delete
        """
        files_to_cleanup = []
        
        # 1. Original video file
        if context.video_path:
            files_to_cleanup.append(context.video_path)
        
        # 2. Encrypted video file (if encryption was performed)
        if context.encrypted_video_path:
            files_to_cleanup.append(context.encrypted_video_path)
        
        # 3. Encryption metadata file (if encryption was performed)
        if context.encryption_metadata and context.encryption_metadata.ciphertext:
            # Metadata file is typically at ciphertext_path + ".meta" or derived from it
            metadata_path = self._get_metadata_path(context)
            if metadata_path:
                files_to_cleanup.append(metadata_path)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for f in files_to_cleanup:
            if f and f not in seen:
                seen.add(f)
                unique_files.append(f)
        
        return unique_files
    
    def _get_metadata_path(self, context: PipelineContext) -> Optional[str]:
        """Get the path to the encryption metadata file.
        
        The metadata file path can be stored in different places depending
        on how the encryption was performed.
        
        Args:
            context: Pipeline context
            
        Returns:
            Path to metadata file or None if not found
        """
        # Check if metadata path was stored in step_data by encrypt_step
        metadata_path = context.get_step_data("encrypt", "metadata_path", None)
        if metadata_path and os.path.exists(metadata_path):
            return metadata_path
        
        # Derive metadata path from encrypted file path
        if context.encrypted_video_path:
            # Try common metadata file patterns
            potential_paths = [
                f"{context.encrypted_video_path}.meta",
                f"{context.encrypted_video_path}.metadata",
                context.encrypted_video_path.replace(".encrypted", ".encrypted.meta"),
            ]
            
            for path in potential_paths:
                if os.path.exists(path):
                    return path
        
        return None
    
    async def _delete_file(self, file_path: str) -> None:
        """Delete a single file.
        
        Args:
            file_path: Path to the file to delete
        """
        try:
            path = Path(file_path)
            
            if not path.exists():
                self._files_missing.append(file_path)
                logger.debug(f"File already missing (no cleanup needed): {file_path}")
                return
            
            if not path.is_file():
                logger.warning(f"Path is not a file, skipping: {file_path}")
                return
            
            # Get file size before deletion for reporting
            try:
                file_size = path.stat().st_size
            except OSError:
                file_size = 0
            
            # Delete the file
            path.unlink()
            
            self._files_deleted.append(file_path)
            self._bytes_freed += file_size
            
            logger.debug(f"Deleted: {file_path} ({file_size} bytes)")
            
        except PermissionError:
            logger.warning(f"Permission denied deleting file: {file_path}")
        except OSError as e:
            logger.warning(f"Error deleting file {file_path}: {e}")
    
    async def on_skip(self, context: PipelineContext, reason: str) -> None:
        """Handle step skip.
        
        Args:
            context: Pipeline context
            reason: Reason for skipping
        """
        logger.debug(f"Cleanup step skipped: {reason}")
