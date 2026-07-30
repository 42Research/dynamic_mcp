#!/usr/bin/env python3
"""
Tunnel Manager for Dynamic MCP Server

Manages cloudflared tunnel setup for reverse connection to Dynamic service.
"""

import asyncio
import logging
import os
import platform
import re
import stat
import subprocess
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class TunnelManager:
    """Manages cloudflared tunnel for exposing the MCP server publicly."""

    def __init__(self, local_port: int):
        """Initialize tunnel manager.
        
        Args:
            local_port: Local port to expose via tunnel
        """
        self.local_port = local_port
        self.tunnel_process: Optional[subprocess.Popen] = None
        self.tunnel_url: Optional[str] = None

    async def ensure_cloudflared_installed(self) -> None:
        """Ensure cloudflared is installed on the system."""
        try:
            subprocess.run(
                ["cloudflared", "--version"],
                capture_output=True,
                check=True,
                timeout=5
            )
            logger.info("✓ cloudflared is already installed")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        logger.info("cloudflared not found, downloading binary from GitHub releases...")
        await self._download_cloudflared()

    async def _download_cloudflared(self) -> None:
        """Download cloudflared binary directly from GitHub releases."""
        system = platform.system()
        machine = platform.machine().lower()

        arch_map = {
            "x86_64": "amd64",
            "amd64": "amd64",
            "aarch64": "arm64",
            "arm64": "arm64",
            "armv7l": "arm",
            "armv6l": "arm",
        }
        arch = arch_map.get(machine)

        _install_hint = (
            "Please install cloudflared manually: "
            "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
        )

        if not arch:
            raise RuntimeError(f"Unsupported architecture: {machine}. {_install_hint}")

        if system == "Linux":
            asset = f"cloudflared-linux-{arch}"
        elif system == "Darwin":
            asset = f"cloudflared-darwin-{arch}.tgz"
        elif system == "Windows":
            asset = f"cloudflared-windows-{arch}.exe"
        else:
            raise RuntimeError(f"Unsupported OS: {system}. {_install_hint}")

        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{asset}"

        # Prefer ~/.local/bin so we don't need root; fall back to /usr/local/bin
        if system != "Windows" and os.geteuid() == 0:
            install_path = "/usr/local/bin/cloudflared"
        else:
            local_bin = os.path.expanduser("~/.local/bin")
            os.makedirs(local_bin, exist_ok=True)
            install_path = os.path.join(local_bin, "cloudflared")

        logger.info(f"Downloading {url} → {install_path}")
        try:
            urllib.request.urlretrieve(url, install_path)
        except Exception as e:
            raise RuntimeError(f"Failed to download cloudflared: {e}. {_install_hint}")

        if system != "Windows":
            os.chmod(install_path, os.stat(install_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # Verify the binary works
        try:
            subprocess.run([install_path, "--version"], capture_output=True, check=True, timeout=5)
            logger.info(f"✓ cloudflared installed to {install_path}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"cloudflared binary verification failed: {e}. {_install_hint}")

    async def start_tunnel(self) -> str:
        """Start the cloudflared tunnel.

        Returns:
            The public tunnel URL

        Raises:
            RuntimeError: If tunnel fails to start
        """
        try:
            # Ensure cloudflared is installed
            await self.ensure_cloudflared_installed()

            logger.info("Starting cloudflared tunnel...")
            logger.info(f"Exposing http://localhost:{self.local_port} to the internet...")

            # Start the tunnel process using asyncio subprocess
            self.tunnel_process = await asyncio.create_subprocess_exec(
                "cloudflared", "tunnel", "--url", f"http://localhost:{self.local_port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Extract tunnel URL from output
            self.tunnel_url = await self._extract_tunnel_url()

            if not self.tunnel_url:
                raise RuntimeError("Failed to extract tunnel URL from cloudflared output")

            logger.info("✓ Tunnel started successfully")
            logger.info(f"✓ Public URL: {self.tunnel_url}")

            return self.tunnel_url

        except Exception as e:
            logger.error(f"✗ Failed to start tunnel: {e}")
            if self.tunnel_process:
                self.tunnel_process.terminate()
                try:
                    await self.tunnel_process.wait()
                except:
                    pass
                self.tunnel_process = None
            raise

    async def _extract_tunnel_url(self) -> Optional[str]:
        """Extract tunnel URL from cloudflared output."""
        timeout = 30  # 30 second timeout (cloudflared can be slow)
        start_time = asyncio.get_event_loop().time()

        try:
            while self.tunnel_process:
                # Check timeout
                if asyncio.get_event_loop().time() - start_time > timeout:
                    logger.warning("Timeout waiting for tunnel URL")
                    return None

                try:
                    # Read from stderr (cloudflared outputs to stderr)
                    line = await asyncio.wait_for(
                        self.tunnel_process.stderr.readline(),
                        timeout=1.0
                    )

                    if not line:
                        # Process ended
                        break

                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if line_str:
                        logger.info(f"[TUNNEL] {line_str}")
                        # Look for the tunnel URL
                        match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line_str)
                        if match:
                            return match.group(0)

                except asyncio.TimeoutError:
                    # No data available, continue waiting
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error reading tunnel output: {e}")
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in tunnel URL extraction: {e}")
            return None

        return None

    async def stop_tunnel(self) -> None:
        """Stop the cloudflared tunnel."""
        try:
            if not self.tunnel_process:
                logger.info("Tunnel is not running")
                return

            logger.info("Stopping cloudflared tunnel...")
            self.tunnel_process.terminate()
            try:
                await asyncio.wait_for(self.tunnel_process.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Tunnel process did not stop gracefully, killing...")
                self.tunnel_process.kill()
                try:
                    await self.tunnel_process.wait()
                except:
                    pass

            self.tunnel_process = None
            self.tunnel_url = None

            logger.info("✓ Tunnel stopped")

        except Exception as e:
            logger.error(f"Error stopping tunnel: {e}")

    def get_tunnel_url(self) -> Optional[str]:
        """Get the current tunnel URL."""
        return self.tunnel_url

    def is_running(self) -> bool:
        """Check if tunnel is running."""
        return (
            self.tunnel_process is not None
            and self.tunnel_process.returncode is None
            and self.tunnel_url is not None
        )

