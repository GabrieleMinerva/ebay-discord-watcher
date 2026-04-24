import os
import unittest
from unittest.mock import patch

from app.main import start_health_server_if_needed


class RuntimeHealthTests(unittest.TestCase):
    @patch("app.main.threading.Thread")
    def test_health_server_not_started_without_port(self, mock_thread):
        with patch.dict(os.environ, {}, clear=True):
            start_health_server_if_needed()
        mock_thread.assert_not_called()

    @patch("app.main.threading.Thread")
    def test_health_server_started_with_valid_port(self, mock_thread):
        with patch.dict(os.environ, {"PORT": "10000"}, clear=True):
            start_health_server_if_needed()
        mock_thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
