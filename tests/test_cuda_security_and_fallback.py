import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.system_resource_manager import (
    configure_windows_cuda_dll_directories,
    is_trusted_cuda_directory,
    reset_cuda_dll_directories,
    _REGISTERED_CUDA_DIRECTORIES,
    _REGISTERED_CUDA_COOKIE_HANDLES
)
from core.transcriber import SpeechTranscriber

class TestCudaSecurityAndFallback(unittest.TestCase):
    def setUp(self):
        reset_cuda_dll_directories()

    def tearDown(self):
        reset_cuda_dll_directories()

    def test_untrusted_directories_rejected(self):
        temp_dir = tempfile.gettempdir()
        self.assertFalse(is_trusted_cuda_directory(temp_dir), "Temp directory must be rejected")
        
        user_dl = os.path.expanduser("~\\Downloads")
        self.assertFalse(is_trusted_cuda_directory(user_dl), "Downloads directory must be rejected")
        
        user_desk = os.path.expanduser("~\\Desktop")
        self.assertFalse(is_trusted_cuda_directory(user_desk), "Desktop directory must be rejected")

        self.assertFalse(is_trusted_cuda_directory(""), "Empty directory must be rejected")
        self.assertFalse(is_trusted_cuda_directory(None), "None directory must be rejected")

    def test_trusted_directories_accepted(self):
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        cuda_path = os.path.join(prog_files, "NVIDIA GPU Computing Toolkit", "CUDA", "v12.4", "bin")
        self.assertTrue(is_trusted_cuda_directory(cuda_path), "Program Files path should be trusted")

    def test_stub_dll_rejected(self):
        """Verifies that an abnormally small cublas DLL is rejected for security."""
        with tempfile.TemporaryDirectory() as td:
            stub_dll = os.path.join(td, "cublas64_12.dll")
            with open(stub_dll, "wb") as f:
                f.write(b"NOT A REAL DLL")  # Only 14 bytes

            # Even if mocked as trusted, small file size should reject it
            with patch("core.system_resource_manager.is_trusted_cuda_directory", return_value=True):
                with patch("os.path.isdir", return_value=True):
                    with patch("core.system_resource_manager.candidate_dirs", [td], create=True):
                        # Reset and run configure
                        reset_cuda_dll_directories()
                        # Call configure
                        res = configure_windows_cuda_dll_directories()
                        self.assertNotIn(td, res)

    def test_cookie_handles_preserved(self):
        """Verifies that os.add_dll_directory return cookies are preserved to prevent premature GC."""
        mock_cookie = MagicMock()
        with patch("os.path.isdir", return_value=True), \
             patch("core.system_resource_manager.is_trusted_cuda_directory", return_value=True), \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.islink", return_value=False), \
             patch("os.path.getsize", return_value=50 * 1024 * 1024), \
             patch("os.add_dll_directory", return_value=mock_cookie) as mock_add_dll:
            
            fake_dir = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin"
            with patch("core.system_resource_manager.candidate_dirs", [fake_dir], create=True):
                reset_cuda_dll_directories()
                # Run configure
                with patch.dict(os.environ, {"CUDA_PATH": r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4"}):
                    res = configure_windows_cuda_dll_directories()
                    if hasattr(os, "add_dll_directory"):
                        from core.system_resource_manager import _REGISTERED_CUDA_COOKIE_HANDLES
                        self.assertIn(mock_cookie, _REGISTERED_CUDA_COOKIE_HANDLES)

    def test_transcriber_initialization_cuda_failure_recovers_to_cpu(self):
        """Verifies SpeechTranscriber falls back cleanly to CPU when CUDA init fails."""
        transcriber = SpeechTranscriber(model_size="tiny.en", device="cuda")
        transcriber._determine_target_device = MagicMock(return_value=("cuda", "float16"))
        
        def mock_whisper_model(model_size, **kwargs):
            if kwargs.get("device") == "cuda":
                raise RuntimeError("cublas64_12.dll not found")
            mock_model = MagicMock()
            return mock_model

        with patch("faster_whisper.WhisperModel", side_effect=mock_whisper_model):
            transcriber._load_model()
            self.assertEqual(transcriber.actual_device, "cpu")
            self.assertIsNotNone(transcriber._model)

    def test_transcriber_runtime_cuda_failure_recovers_to_cpu(self):
        """Verifies SpeechTranscriber falls back cleanly to CPU when runtime CUDA inference fails."""
        transcriber = SpeechTranscriber(model_size="tiny.en", device="cpu")
        transcriber.actual_device = "cuda"
        transcriber.status = "STT_READY"
        transcriber._ready_event.set()
        
        mock_cuda_model = MagicMock()
        mock_cuda_model.transcribe.side_effect = RuntimeError("CUDA out of memory")
        transcriber._model = mock_cuda_model

        mock_cpu_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Hello world"
        mock_segment.avg_logprob = -0.1
        mock_info = MagicMock()
        mock_info.duration = 1.0
        mock_info.language = "en"
        mock_info.language_probability = 0.99
        mock_cpu_model.transcribe.return_value = ([mock_segment], mock_info)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(b"RIFF....WAVEfmt ....data....")
            temp_wav = tf.name

        try:
            with patch("faster_whisper.WhisperModel", return_value=mock_cpu_model):
                text = transcriber.transcribe(temp_wav)
                self.assertEqual(text, "Hello world")
                self.assertEqual(transcriber.actual_device, "cpu")
        finally:
            if os.path.exists(temp_wav):
                os.remove(temp_wav)

if __name__ == "__main__":
    unittest.main()
