"""Encrypt step - Lit Protocol encryption.

This step encrypts video content using Lit Protocol for
access-controlled decryption. It:
1. Connects to Lit Protocol network
2. Encrypts the video file
3. Stores encryption metadata (access conditions, ciphertext hash)

The step uses the JS Runtime Bridge to communicate with the
Lit Protocol SDK running in a Deno subprocess.

The step is conditional and can be skipped via the encrypt option.

Task 12: Writes progress to EncryptionJob and PipelineSnapshot tables.
"""

import asyncio
import base64
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from haven_cli.js_runtime.bridge import JSRuntimeBridge
from haven_cli.js_runtime.manager import JSBridgeManager
from haven_cli.pipeline.context import EncryptionMetadata, PipelineContext
from haven_cli.pipeline.events import EventType
from haven_cli.pipeline.results import StepError, StepResult
from haven_cli.pipeline.step import ConditionalStep
from haven_cli.services.blockchain_network import get_network_config
from haven_cli.services.evm_utils import get_wallet_address_from_private_key

logger = logging.getLogger(__name__)


class EncryptStep(ConditionalStep):
    """Pipeline step for Lit Protocol encryption.
    
    This step encrypts video content using Lit Protocol, enabling
    access-controlled decryption based on on-chain conditions.
    
    The encryption is performed via the JS Runtime Bridge, which
    communicates with the Lit SDK running in a Deno subprocess.
    
    Supports multiple access control patterns:
    - owner_only: Only the wallet owner can decrypt
    - nft_gated: Only NFT holders can decrypt
    - token_gated: Only token holders can decrypt
    - public: Anyone can decrypt (for public content)
    - custom: Explicit access conditions provided in context
    
    Emits:
        - ENCRYPT_REQUESTED event when starting
        - ENCRYPT_PROGRESS events during encryption
        - ENCRYPT_COMPLETE event on success
    
    Output data:
        - ciphertext_hash: Hash of the encrypted content
        - access_conditions: Access control conditions used
        - chain: Blockchain used for access control
        - encrypted_path: Path to the encrypted file
    
    Task 12: Creates/updates EncryptionJob and PipelineSnapshot records.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the encrypt step.
        
        Args:
            config: Step configuration (passed to base class)
        """
        super().__init__(config=config)
        self._job_id: Optional[int] = None
        self._start_time: Optional[float] = None
    
    @property
    def name(self) -> str:
        """Step identifier."""
        return "encrypt"
    
    @property
    def enabled_option(self) -> str:
        """Context option that enables this step."""
        return "encrypt"
    
    @property
    def default_enabled(self) -> bool:
        """Encryption is disabled by default."""
        return False
    
    @property
    def max_retries(self) -> int:
        """Maximum retry attempts for transient errors."""
        return 3
    
    async def process(self, context: PipelineContext) -> StepResult:
        """Process Lit Protocol encryption.
        
        Args:
            context: Pipeline context with video path
            
        Returns:
            StepResult with encryption metadata
        """
        video_path = context.video_path
        self._start_time = time.time()
        
        # Create EncryptionJob record for tracking
        if context.video_id:
            file_size = context.video_metadata.file_size if context.video_metadata else 0
            self._job_id = await self._create_encryption_job(context.video_id, file_size)
            await self._update_pipeline_snapshot(context.video_id, "encrypt", 0)
        
        # Emit encrypt requested event
        await self._emit_event(EventType.ENCRYPT_REQUESTED, context, {
            "video_path": video_path,
        })
        
        try:
            # Get access conditions from config or context
            access_conditions = self._get_access_conditions(context)
            logger.info(f"Using access pattern: {context.options.get('access_pattern', 'owner_only')}")
            
            # Encrypt via Lit Protocol with progress tracking
            # Uses _js_call_with_retry internally for resilience
            encryption_result = await self._encrypt_with_lit(
                video_path,
                access_conditions,
                context,
            )
            
            # Create encryption metadata
            encryption_metadata = EncryptionMetadata(
                ciphertext=encryption_result.get("ciphertext_path", ""),
                data_to_encrypt_hash=encryption_result.get("data_to_encrypt_hash", ""),
                encrypted_key=encryption_result.get("encrypted_key", ""),
                key_hash=encryption_result.get("key_hash", ""),
                iv=encryption_result.get("iv", ""),
                access_control_conditions=access_conditions,
                chain=encryption_result.get("chain", "ethereum"),
            )
            
            # Store in context
            context.encryption_metadata = encryption_metadata
            context.encrypted_video_path = encryption_result.get("ciphertext_path")
            
            # Store original hash for lit_encryption_metadata
            if encryption_result.get("original_hash"):
                context.set_step_data("encrypt", "original_hash", encryption_result.get("original_hash"))
            
            # Save encryption metadata to database
            if context.video_id:
                await self._save_encryption_metadata(
                    context.video_id,
                    encryption_metadata,
                )
            
            # Mark job as completed
            if self._job_id and context.video_id:
                await self._complete_encryption_job(self._job_id, encryption_metadata.data_to_encrypt_hash)
                await self._update_pipeline_snapshot(context.video_id, "encrypt", 100, status="completed")
            
            # Emit encrypt complete event
            await self._emit_event(EventType.ENCRYPT_COMPLETE, context, {
                "video_path": video_path,
                "encrypted_path": encryption_result.get("ciphertext_path"),
                "data_to_encrypt_hash": encryption_metadata.data_to_encrypt_hash,
                "chain": encryption_metadata.chain,
            })
            
            return StepResult.ok(
                self.name,
                ciphertext_hash=encryption_metadata.data_to_encrypt_hash,
                access_conditions=access_conditions,
                chain=encryption_metadata.chain,
                encrypted_path=encryption_result.get("ciphertext_path"),
            )
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            
            # Mark job as failed
            error_msg = str(e)
            if self._job_id and context.video_id:
                await self._fail_encryption_job(self._job_id, error_msg)
                await self._update_pipeline_snapshot(
                    context.video_id, "encrypt", 0, status="failed", error=error_msg
                )
            
            return StepResult.fail(
                self.name,
                StepError.from_exception(e, code="ENCRYPT_ERROR"),
            )
    
    async def _get_js_bridge(self) -> JSRuntimeBridge:
        """Get the JS Runtime Bridge for Lit SDK communication.
        
        Uses the JSBridgeManager singleton for connection reuse and
        automatic reconnection handling.
        
        Returns:
            JSRuntimeBridge instance ready for Lit SDK calls.
        """
        return await JSBridgeManager.get_instance().get_bridge()
    
    async def _js_call_with_retry(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
    ) -> Any:
        """Call JS runtime method with automatic retry on bridge failure.
        
        This method wraps JSBridgeManager.call_with_retry() to handle
        bridge restart scenarios gracefully. When the bridge is stopped
        (e.g., due to health check failure or concurrent operation timeout),
        this method will automatically retry with a fresh bridge.
        
        Args:
            method: The method name to call
            params: Optional parameters for the method
            timeout: Optional timeout override
            max_retries: Maximum retry attempts (default 3)
            
        Returns:
            The result from the JS runtime
            
        Raises:
            RuntimeError: If all retry attempts fail
        """
        return await JSBridgeManager.get_instance().call_with_retry(
            method, params, max_retries=max_retries, timeout=timeout
        )
    
    async def _encrypt_with_lit(
        self,
        video_path: str,
        access_conditions: List[Dict[str, Any]],
        context: PipelineContext,
    ) -> Dict[str, Any]:
        """Encrypt content using Lit Protocol via JS bridge.
        
        The process:
        1. Ensure Lit Protocol connection
        2. Call Lit SDK encryptFile function via bridge with progress tracking
        3. Return encryption metadata
        
        Uses hybrid encryption (AES-256-GCM + Lit Protocol) with chunked
        encryption for progress reporting on large files.
        
        Uses _js_call_with_retry for all JS runtime calls to handle
        bridge restart scenarios gracefully during concurrent operations.
        
        Task 12: Receives progress notifications and updates database tables.
        
        Args:
            video_path: Path to video file
            access_conditions: Access control conditions
            context: Pipeline context for progress updates
            
        Returns:
            Dictionary with encryption result including:
            - ciphertext_path: Path to encrypted file
            - data_to_encrypt_hash: Hash of original content
            - access_control_condition_hash: Hash of access conditions
            - chain: Blockchain used
            
        Raises:
            RuntimeError: If encryption fails
            FileNotFoundError: If video file doesn't exist
        """
        import os
        import hashlib
        
        # Get network configuration (from blockchain.network_mode)
        network_mode = self._config.get("network_mode", "testnet")
        network_config = get_network_config(network_mode)
        
        # Ensure Lit is connected - use network mode config
        lit_network = self._config.get("lit_network") or network_config.lit_network
        chain = self._config.get("chain") or network_config.chain_for_access_control
        
        logger.info(f"Connecting to Lit Protocol network: {lit_network} (mode: {network_mode})")
        
        try:
            # Use longer timeout for Lit connection (testnet can be slow)
            await self._js_call_with_retry("lit.connect", {
                "network": lit_network,
            }, timeout=120.0)  # 2 minutes for connection
        except Exception as e:
            logger.error(f"Failed to connect to Lit Protocol: {e}")
            raise RuntimeError(f"Lit Protocol connection failed: {e}") from e
        
        # Check file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        file_size = os.path.getsize(video_path)
        logger.info(f"Encrypting video file: {video_path} ({file_size} bytes)")
        
        # Get private key for encryption
        private_key = os.environ.get("HAVEN_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
        if not private_key:
            raise RuntimeError("Private key required for encryption. Set HAVEN_PRIVATE_KEY environment variable.")
        
        # Get bridge for progress notifications
        bridge = await self._get_js_bridge()
        
        # Set up progress notification handler
        last_progress = [0]  # Use list to allow mutation in nested function
        
        def handle_encrypt_progress(params: dict) -> None:
            """Handle encryption progress notifications from JS runtime."""
            percent = params.get("percent", 0)
            message = params.get("message", "")
            bytes_processed = params.get("bytesProcessed", 0)
            total_bytes = params.get("totalBytes", file_size)
            
            # Only emit events for meaningful progress changes (every 5%)
            if percent - last_progress[0] >= 5 or percent >= 100:
                last_progress[0] = percent
                
                # Calculate encryption speed
                if self._start_time:
                    elapsed = time.time() - self._start_time
                    encrypt_speed = int(bytes_processed / elapsed) if elapsed > 0 else 0
                else:
                    encrypt_speed = 0
                
                # Update job progress in database
                if self._job_id and context.video_id:
                    asyncio.create_task(
                        self._update_job_progress(
                            context.video_id, bytes_processed, percent, total_bytes, encrypt_speed
                        )
                    )
                
                # Emit progress event
                asyncio.create_task(
                    self._emit_event(EventType.ENCRYPT_PROGRESS, context, {
                        "video_id": context.video_id,
                        "job_id": self._job_id,
                        "progress": percent,
                        "message": message,
                        "speed": encrypt_speed,
                        "bytes_processed": bytes_processed,
                        "bytes_total": total_bytes,
                        "stage": "encrypting" if percent < 100 else "complete",
                    })
                )
        
        # Register for progress notifications
        unregister_progress = bridge.on_notification("lit.encryptProgress", handle_encrypt_progress)
        
        try:
            # Emit progress event - starting
            await self._emit_event(EventType.ENCRYPT_PROGRESS, context, {
                "video_id": context.video_id,
                "job_id": self._job_id,
                "progress": 0,
                "stage": "encrypting",
            })
            
            # Call encryptFile with progress tracking enabled
            # This uses hybrid encryption (AES-256-GCM + Lit Protocol)
            # Calculate timeout based on file size: base 2 min + 1 min per 100MB
            encrypt_timeout = 120.0 + (file_size / (100 * 1024 * 1024)) * 60.0
            encrypt_timeout = min(encrypt_timeout, 600.0)  # Cap at 10 minutes
            logger.debug(f"Encryption timeout: {encrypt_timeout:.0f}s for {file_size} bytes")
            
            result = await self._js_call_with_retry("lit.encryptFile", {
                "filePath": video_path,
                "chain": chain,
                "privateKey": private_key,
                "onProgress": True,  # Request progress notifications
            }, timeout=encrypt_timeout)
            
            # Extract result data
            encrypted_path = result.get("encryptedFilePath", "")
            metadata = result.get("metadata", {})
            
            # Extract Lit encryption metadata for lit_encryption_metadata
            encrypted_key = metadata.get("encryptedKey", "")
            key_hash = metadata.get("keyHash", "")
            iv = metadata.get("iv", "")
            
            # Calculate original file hash for integrity verification
            original_hash = hashlib.sha256(open(video_path, "rb").read()).hexdigest()
            
            # Final progress update
            if self._job_id and context.video_id:
                await self._update_job_progress(context.video_id, file_size, 100, file_size)
            
            # Emit progress event - complete
            await self._emit_event(EventType.ENCRYPT_PROGRESS, context, {
                "video_id": context.video_id,
                "job_id": self._job_id,
                "progress": 100,
                "speed": file_size,
                "stage": "complete",
            })
            
            logger.info(f"Encryption complete. Encrypted file: {encrypted_path}")
            
            return {
                "ciphertext_path": encrypted_path,
                "data_to_encrypt_hash": metadata.get("keyHash", ""),
                "access_control_condition_hash": "",  # Not returned by hybrid encryption
                "chain": chain,
                "original_hash": original_hash,
                "metadata_path": result.get("metadataPath", ""),
                "encrypted_key": encrypted_key,
                "key_hash": key_hash,
                "iv": iv,
            }
            
        finally:
            # Unregister progress handler
            unregister_progress()
    
    def _get_access_conditions(
        self,
        context: PipelineContext,
    ) -> List[Dict[str, Any]]:
        """Get access control conditions for encryption.
        
        Access conditions define who can decrypt the content.
        They can be based on:
        - Wallet address ownership (owner_only)
        - NFT ownership (nft_gated)
        - Token balance (token_gated)
        - Public access (public)
        - Custom conditions provided in context
        
        Args:
            context: Pipeline context with options
            
        Returns:
            List of access control condition dictionaries
            
        Raises:
            ValueError: If unknown access pattern or missing required options
        """
        # Check for explicit conditions in context options
        if "access_conditions" in context.options:
            return context.options["access_conditions"]
        
        # Check for preset patterns
        pattern = context.options.get("access_pattern", "owner_only")
        
        if pattern == "owner_only":
            return self._owner_only_conditions(context)
        elif pattern == "nft_gated":
            return self._nft_gated_conditions(context)
        elif pattern == "token_gated":
            return self._token_gated_conditions(context)
        elif pattern == "public":
            return self._public_conditions()
        else:
            raise ValueError(f"Unknown access pattern: {pattern}")
    
    def _owner_only_conditions(self, context: PipelineContext) -> List[Dict[str, Any]]:
        """Access restricted to wallet owner.
        
        Args:
            context: Pipeline context
            
        Returns:
            Access control conditions for owner-only access
            
        Raises:
            ValueError: If owner_wallet not configured and cannot be derived
        """
        wallet_address = context.options.get("owner_wallet") or self._config.get("owner_wallet")
        
        # Auto-derive owner_wallet from private key if not explicitly set
        if not wallet_address:
            private_key = os.environ.get("HAVEN_PRIVATE_KEY")
            if private_key:
                wallet_address = get_wallet_address_from_private_key(private_key)
                if wallet_address and wallet_address != "unknown":
                    logger.info(f"Auto-derived owner_wallet from private key: {wallet_address}")
        
        if not wallet_address:
            raise ValueError("owner_wallet required for owner_only pattern. "
                           "Set it in config, context options, or provide HAVEN_PRIVATE_KEY env var.")
        
        chain = self._config.get("chain", "ethereum")
        
        return [{
            "contractAddress": "",
            "standardContractType": "",
            "chain": chain,
            "method": "",
            "parameters": [":userAddress"],
            "returnValueTest": {
                "comparator": "=",
                "value": wallet_address,
            },
        }]
    
    def _nft_gated_conditions(self, context: PipelineContext) -> List[Dict[str, Any]]:
        """Access restricted to NFT holders.
        
        Args:
            context: Pipeline context with nft_contract option
            
        Returns:
            Access control conditions for NFT-gated access
            
        Raises:
            ValueError: If nft_contract not provided
        """
        contract = context.options.get("nft_contract") or self._config.get("nft_contract")
        if not contract:
            raise ValueError("nft_contract required for nft_gated pattern. "
                           "Set it in context options or config.")
        
        chain = self._config.get("chain", "ethereum")
        
        return [{
            "contractAddress": contract,
            "standardContractType": "ERC721",
            "chain": chain,
            "method": "balanceOf",
            "parameters": [":userAddress"],
            "returnValueTest": {
                "comparator": ">",
                "value": "0",
            },
        }]
    
    def _token_gated_conditions(self, context: PipelineContext) -> List[Dict[str, Any]]:
        """Access restricted to token holders.
        
        Requires a minimum token balance to decrypt.
        
        Args:
            context: Pipeline context with token_contract and min_balance options
            
        Returns:
            Access control conditions for token-gated access
            
        Raises:
            ValueError: If token_contract or min_balance not provided
        """
        contract = context.options.get("token_contract") or self._config.get("token_contract")
        if not contract:
            raise ValueError("token_contract required for token_gated pattern")
        
        min_balance = context.options.get("min_balance") or self._config.get("min_balance", "1")
        chain = self._config.get("chain", "ethereum")
        
        # Determine token standard (default to ERC20)
        token_standard = context.options.get("token_standard") or self._config.get("token_standard", "ERC20")
        
        if token_standard == "ERC20":
            return [{
                "contractAddress": contract,
                "standardContractType": "ERC20",
                "chain": chain,
                "method": "balanceOf",
                "parameters": [":userAddress"],
                "returnValueTest": {
                    "comparator": ">=",
                    "value": str(min_balance),
                },
            }]
        elif token_standard == "ERC721":
            # For ERC721, use balanceOf like NFT gating
            return [{
                "contractAddress": contract,
                "standardContractType": "ERC721",
                "chain": chain,
                "method": "balanceOf",
                "parameters": [":userAddress"],
                "returnValueTest": {
                    "comparator": ">=",
                    "value": str(min_balance),
                },
            }]
        else:
            raise ValueError(f"Unsupported token standard: {token_standard}")
    
    def _public_conditions(self) -> List[Dict[str, Any]]:
        """Public access conditions - anyone can decrypt.
        
        This creates a condition that always returns true.
        Note: In practice, this may still require a valid wallet signature
        but doesn't restrict based on ownership.
        
        Returns:
            Access control conditions allowing public access
        """
        chain = self._config.get("chain", "ethereum")
        
        return [{
            "contractAddress": "",
            "standardContractType": "",
            "chain": chain,
            "method": "",
            "parameters": [],
            "returnValueTest": {
                "comparator": "=",
                "value": "true",
            },
        }]
    
    async def _save_encryption_metadata(
        self,
        video_id: int,
        metadata: EncryptionMetadata,
    ) -> None:
        """Save encryption metadata to database.
        
        Args:
            video_id: ID of the video record
            metadata: Encryption metadata to save
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import VideoRepository
            
            with get_db_session() as session:
                repo = VideoRepository(session)
                video = repo.get_by_id(video_id)
                
                if video:
                    repo.update(
                        video,
                        encrypted=True,
                        lit_encryption_metadata=self._metadata_to_json(metadata),
                    )
                    logger.info(f"Saved encryption metadata for video {video_id}")
                else:
                    logger.warning(f"Video {video_id} not found, cannot save encryption metadata")
                    
        except Exception as e:
            # Log error but don't fail the step - encryption succeeded
            logger.error(f"Failed to save encryption metadata to database: {e}")
    
    def _metadata_to_json(self, metadata: EncryptionMetadata) -> str:
        """Convert encryption metadata to JSON string.
        
        Args:
            metadata: Encryption metadata
            
        Returns:
            JSON string representation
        """
        import json
        return json.dumps({
            "ciphertext": metadata.ciphertext,
            "data_to_encrypt_hash": metadata.data_to_encrypt_hash,
            "dataToEncryptHash": metadata.data_to_encrypt_hash,  # camelCase for JS compatibility
            "encrypted_key": metadata.encrypted_key,
            "encryptedKey": metadata.encrypted_key,  # camelCase for JS compatibility
            "key_hash": metadata.key_hash,
            "keyHash": metadata.key_hash,  # camelCase for JS compatibility
            "iv": metadata.iv,
            "access_control_conditions": metadata.access_control_conditions,
            "accessControlConditions": metadata.access_control_conditions,  # camelCase
            "chain": metadata.chain,
        })
    
    async def on_skip(self, context: PipelineContext, reason: str) -> None:
        """Handle step skip - encryption not requested."""
        logger.debug(f"Encrypt step skipped: {reason}")
        
        # Create a skipped EncryptionJob record so TUI shows correct status
        if context.video_id:
            await self._create_skipped_encryption_job(context.video_id, reason)
    
    async def on_error(
        self,
        context: PipelineContext,
        error: Optional[StepError],
    ) -> None:
        """Handle encryption error."""
        logger.error(f"Encryption step failed: {error.message if error else 'Unknown error'}")
    
    # =========================================================================
    # Task 12: Job tracking helper methods
    # =========================================================================
    
    async def _create_encryption_job(
        self,
        video_id: int,
        bytes_total: int,
    ) -> Optional[int]:
        """Create an EncryptionJob record for tracking.
        
        Args:
            video_id: Video ID
            bytes_total: Total bytes to encrypt
            
        Returns:
            Job ID or None if creation failed
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import EncryptionJobRepository
            
            with get_db_session() as session:
                repo = EncryptionJobRepository(session)
                job = repo.create(
                    video_id=video_id,
                    status="encrypting",
                    bytes_total=bytes_total,
                )
                logger.debug(f"Created EncryptionJob {job.id} for video {video_id}")
                return job.id
        except Exception as e:
            logger.warning(f"Failed to create EncryptionJob: {e}")
            return None
    
    async def _create_skipped_encryption_job(
        self,
        video_id: int,
        reason: str,
    ) -> Optional[int]:
        """Create an EncryptionJob record marked as skipped.
        
        This is called when encryption is skipped due to configuration
        (encrypt=false) so the TUI correctly shows encryption as skipped
        rather than pending.
        
        Args:
            video_id: Video ID
            reason: Reason for skipping (e.g., "encrypt is disabled")
            
        Returns:
            Job ID or None if creation failed
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import EncryptionJobRepository
            
            with get_db_session() as session:
                repo = EncryptionJobRepository(session)
                job = repo.create(
                    video_id=video_id,
                    status="skipped",
                    bytes_total=0,
                )
                # Update with skip reason
                job.error_message = reason
                session.commit()
                logger.debug(f"Created skipped EncryptionJob {job.id} for video {video_id}")
                return job.id
        except Exception as e:
            logger.warning(f"Failed to create skipped EncryptionJob: {e}")
            return None
    
    async def _update_job_progress(
        self,
        video_id: int,
        bytes_processed: int,
        progress_percent: float,
        bytes_total: int,
        encrypt_speed: int = 0,
    ) -> None:
        """Update EncryptionJob progress.
        
        Args:
            video_id: Video ID
            bytes_processed: Bytes encrypted so far
            progress_percent: Progress percentage (0-100)
            bytes_total: Total bytes to encrypt
            encrypt_speed: Encryption speed in bytes/sec
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import EncryptionJobRepository, PipelineSnapshotRepository
            
            with get_db_session() as session:
                job_repo = EncryptionJobRepository(session)
                if self._job_id:
                    job_repo.update_progress(self._job_id, bytes_processed, encrypt_speed)
                
                # Also update pipeline snapshot
                snapshot_repo = PipelineSnapshotRepository(session)
                snapshot_repo.update_stage(
                    video_id=video_id,
                    stage="encrypt",
                    status="active",
                    progress_percent=progress_percent,
                    stage_speed=encrypt_speed,
                )
                snapshot_repo.update_bytes_metrics(
                    video_id=video_id,
                    encrypted_bytes=bytes_processed,
                )
        except Exception as e:
            logger.debug(f"Failed to update EncryptionJob progress: {e}")
    
    async def _complete_encryption_job(
        self,
        job_id: int,
        lit_cid: Optional[str] = None,
    ) -> None:
        """Mark EncryptionJob as completed.
        
        Args:
            job_id: Job ID
            lit_cid: Lit Protocol CID (if available)
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import EncryptionJobRepository
            
            with get_db_session() as session:
                repo = EncryptionJobRepository(session)
                repo.update_status(job_id, "completed", lit_cid=lit_cid)
                logger.debug(f"Completed EncryptionJob {job_id}")
        except Exception as e:
            logger.warning(f"Failed to complete EncryptionJob: {e}")
    
    async def _fail_encryption_job(self, job_id: int, error_message: str) -> None:
        """Mark EncryptionJob as failed.
        
        Args:
            job_id: Job ID
            error_message: Error description
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import EncryptionJobRepository
            
            with get_db_session() as session:
                repo = EncryptionJobRepository(session)
                repo.update_status(job_id, "failed", error_message=error_message)
                logger.debug(f"Failed EncryptionJob {job_id}: {error_message}")
        except Exception as e:
            logger.warning(f"Failed to mark EncryptionJob as failed: {e}")
    
    async def _update_pipeline_snapshot(
        self,
        video_id: int,
        stage: str,
        progress_percent: float,
        status: str = "active",
        error: Optional[str] = None,
    ) -> None:
        """Update PipelineSnapshot for TUI dashboard.
        
        Args:
            video_id: Video ID
            stage: Current stage name
            progress_percent: Stage progress (0-100)
            status: Overall status
            error: Error message if failed
        """
        try:
            from haven_cli.database.connection import get_db_session
            from haven_cli.database.repositories import PipelineSnapshotRepository
            
            with get_db_session() as session:
                repo = PipelineSnapshotRepository(session)
                
                if status == "failed" and error:
                    repo.mark_error(video_id, stage, error)
                elif status == "completed":
                    repo.mark_completed(video_id)
                else:
                    repo.update_stage(
                        video_id=video_id,
                        stage=stage,
                        status=status,
                        progress_percent=progress_percent,
                    )
        except Exception as e:
            logger.debug(f"Failed to update PipelineSnapshot: {e}")
