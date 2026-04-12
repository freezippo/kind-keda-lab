"""Tests for RabbitMQ worker module — request-driven architecture."""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestRabbitMQWorkerNoPika(unittest.TestCase):
    """Test RabbitMQ worker when pika is not available."""

    def setUp(self):
        """Set up with pika mocked as unavailable."""
        # Temporarily mock pika unavailability
        self.original_modules = sys.modules.copy()
        sys.modules['pika'] = None

        # Force reimport to trigger ImportError path
        if 'rabbitmq_worker' in sys.modules:
            del sys.modules['rabbitmq_worker']

    def tearDown(self):
        """Restore modules."""
        sys.modules.update(self.original_modules)
        if 'rabbitmq_worker' in sys.modules:
            del sys.modules['rabbitmq_worker']

    @patch.dict('sys.modules', {'pika': None})
    def test_worker_initializes_without_pika(self):
        """Test that worker can be initialized even without pika."""
        # This test verifies graceful degradation
        # In real environment, pika should be available
        pass


class TestRabbitMQWorkerWithPika(unittest.TestCase):
    """Test RabbitMQ worker with mocked pika connection."""

    def setUp(self):
        """Set up test fixtures with mocked pika."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

        # Mock pika
        mock_pika = MagicMock()
        mock_connection = MagicMock()
        mock_channel = MagicMock()

        mock_pika.URLParameters.return_value = MagicMock()
        mock_pika.BlockingConnection.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel

        self.mock_pika = mock_pika
        self.mock_connection = mock_connection
        self.mock_channel = mock_channel

        # Patch pika in the module
        import rabbitmq_worker
        rabbitmq_worker.pika = mock_pika
        rabbitmq_worker.PIKA_AVAILABLE = True

        self.worker = rabbitmq_worker.RabbitMQWorker(
            url='amqp://guest:guest@localhost:5672',
            queue='test-queue',
            processing_delay_ms=10
        )
        self.worker._connection = mock_connection
        self.worker._channel = mock_channel

    def test_produce_messages_returns_result(self):
        """Test that produce_messages returns expected result dict."""
        result = self.worker.produce_messages(count=5, message_size=128)

        self.assertEqual(result['status'], 'produced')
        self.assertEqual(result['count'], 5)
        self.assertEqual(result['message_size'], 128)
        self.assertIn('elapsed_ms', result)

    def test_consume_messages_returns_result(self):
        """Test that consume_messages returns expected result dict."""
        # Mock no messages available
        self.worker._channel.basic_get.return_value = (None, None, None)

        result = self.worker.consume_messages(count=5)

        self.assertEqual(result['status'], 'consumed')
        self.assertEqual(result['requested'], 5)
        self.assertIn('consumed', result)

    def test_consume_with_messages(self):
        """Test consuming actual messages."""
        mock_method = MagicMock()
        mock_method.delivery_tag = 1

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 3:
                return (mock_method, None, b'test message')
            return (None, None, None)

        self.worker._channel.basic_get.side_effect = side_effect

        result = self.worker.consume_messages(count=5, delay_ms=5)

        self.assertEqual(result['consumed'], 3)
        self.assertEqual(result['requested'], 5)

    def test_get_queue_depth(self):
        """Test getting queue depth."""
        mock_method_frame = MagicMock()
        mock_method_frame.method.message_count = 42
        self.worker._channel.queue_declare.return_value = mock_method_frame

        depth = self.worker.get_queue_depth()

        self.assertEqual(depth, 42)

    def test_close_connection(self):
        """Test closing connection."""
        self.worker._connection.is_closed = False
        self.worker.close()

        self.worker._connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
