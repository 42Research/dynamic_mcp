"""Crash session management."""

import logging
import pexpect
import subprocess
import time
from typing import Optional, Tuple


logger = logging.getLogger(__name__)


class CrashSession:
    """Represents an active crash analysis session."""

    def __init__(self, dump_path: str, kernel_path: str):
        self.dump_path = dump_path
        self.kernel_path = kernel_path
        self.process = None
        self.session_id = f"crash_{int(time.time())}"
        self.active = False
        self.prompt_patterns = [
            r'crash> ',           # Standard prompt with space
            r'crash>',            # Prompt without space
            r'crash>\s*',         # Prompt with optional whitespace
        ]

    def is_active(self) -> bool:
        """Check if the session is active."""
        return self.active

    def start(self, timeout: int = 180) -> bool:
        """Start the crash session.

        Detects kernel file type and uses appropriate crash command format:
        - For debug symbols (vmlinux): crash --no_scroll vmcore vmlinux
        - For compressed kernels (vmlinuz): crash --no_scroll -f vmlinuz vmcore
        """
        try:
            # Detect kernel file type and build appropriate command
            kernel_name = self.kernel_path.split('/')[-1]
            is_debug_symbol = kernel_name == "vmlinux" or kernel_name.startswith("vmlinux-")

            if is_debug_symbol:
                # Debug symbols: crash --no_scroll vmcore vmlinux (no -f flag needed)
                cmd_parts = ['crash', '--no_scroll', self.dump_path, self.kernel_path]
            else:
                # Compressed kernel: crash --no_scroll -f vmlinuz vmcore
                cmd_parts = ['crash', '--no_scroll', '-f', self.kernel_path, self.dump_path]

            cmd = ' '.join(cmd_parts)

            logger.info(f"Starting crash process: {cmd}")

            # Start crash process
            self.process = pexpect.spawn(cmd, timeout=timeout)

            # Wait for initial prompt
            expect_list = self.prompt_patterns + ['crash: .*', pexpect.TIMEOUT, pexpect.EOF]

            index = self.process.expect(expect_list, timeout=timeout)

            if index < len(self.prompt_patterns):
                logger.info(f"Crash session started successfully: {self.session_id}")
                self.active = True
                return True
            elif index == len(self.prompt_patterns):
                # Error pattern
                error_msg = self.process.after.decode('utf-8', errors='ignore')
                logger.error(f"Crash startup error: {error_msg}")
                return False
            elif index == len(self.prompt_patterns) + 1:
                # Timeout
                logger.error(f"Crash startup timed out after {timeout} seconds")
                return False
            else:
                # EOF
                logger.error("Crash process terminated during startup")
                return False

        except Exception as e:
            logger.error(f"Failed to start crash session: {e}")
            return False
    
    def execute_command(self, command: str, timeout: int = 120) -> Tuple[str, str, int]:
        """Execute a command in the crash session."""
        if not self.is_active() or not self.process:
            return "", "Session not active", 1

        try:
            logger.info(f"Executing crash command: {command}")

            # Send command to crash process
            self.process.sendline(command)

            # Wait for prompt to return
            expect_list = self.prompt_patterns + ['crash: .*', pexpect.TIMEOUT, pexpect.EOF]

            index = self.process.expect(expect_list, timeout=timeout)

            if index < len(self.prompt_patterns):
                # Successfully got prompt back
                output = self.process.before.decode('utf-8', errors='ignore')
                # Clean up the output by removing the command echo
                lines = output.split('\n')
                if lines and lines[0].strip() == command.strip():
                    output = '\n'.join(lines[1:])
                return output.strip(), "", 0
            elif index == len(self.prompt_patterns):
                # Error pattern matched
                error_msg = self.process.after.decode('utf-8', errors='ignore')
                return "", f"Crash error: {error_msg}", 1
            elif index == len(self.prompt_patterns) + 1:
                # Timeout
                return "", f"Command '{command}' timed out after {timeout} seconds", 1
            else:
                # EOF - crash process died
                self.active = False
                return "", "Crash process terminated unexpectedly", 1

        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}")
            return "", str(e), 1
    
    def close(self):
        """Close the crash session."""
        if self.process:
            try:
                # Try to quit gracefully first
                if self.active:
                    try:
                        self.process.sendline('quit')
                        self.process.expect(pexpect.EOF, timeout=5)
                    except:
                        pass

                # Force close if still alive
                if self.process.isalive():
                    self.process.terminate()
                    if self.process.isalive():
                        self.process.kill()

            except Exception as e:
                logger.error(f"Error closing session: {e}")
            finally:
                self.process = None
        self.active = False


class CrashSessionManager:
    """Manages crash analysis sessions."""
    
    def __init__(self):
        self.active_session: Optional[CrashSession] = None
    
    def start_session(self, crash_dump, kernel_file, timeout: int = 180) -> bool:
        """Start a new crash analysis session."""
        # Close existing session if any
        if self.active_session:
            self.close_session()

        try:
            logger.info(f"Starting crash session with dump: {crash_dump.name}, kernel: {kernel_file.name}")

            # Create new session
            session = CrashSession(str(crash_dump.path), str(kernel_file.path))

            # Actually start the crash process
            if session.start(timeout):
                self.active_session = session
                logger.info(f"Crash session started successfully: {session.session_id}")
                return True
            else:
                logger.error("Failed to start crash process")
                return False

        except Exception as e:
            logger.error(f"Failed to start crash session: {e}")
            return False
    
    def execute_command(self, command: str, timeout: int = 120) -> Tuple[str, str, int]:
        """Execute a command in the active session."""
        if not self.active_session:
            return "", "No active crash session", 1
        
        return self.active_session.execute_command(command, timeout)
    
    def is_session_active(self) -> bool:
        """Check if there's an active session."""
        return self.active_session is not None and self.active_session.is_active()
    
    def get_session_info(self) -> dict:
        """Get information about the active session."""
        if not self.active_session:
            return {"active": False}
        
        return {
            "active": True,
            "session_id": self.active_session.session_id,
            "dump_path": self.active_session.dump_path,
            "kernel_path": self.active_session.kernel_path
        }
    
    def close_session(self):
        """Close the active session."""
        if self.active_session:
            logger.info(f"Closing crash session: {self.active_session.session_id}")
            self.active_session.close()
            self.active_session = None
