#!/usr/bin/env python3
"""
Kind-KEDA Lab Workload — Main Entry Point

Multi-purpose Python workload with HTTP server supporting multiple behavior modes
controlled via the MODE environment variable. All modes run an HTTP server where
each request triggers mode-specific processing.

Modes:
    cpu        — HTTP requests trigger CPU-intensive computation
    memory     — HTTP requests trigger memory allocation
    rabbitmq   — HTTP requests trigger message produce/consume operations
    prometheus — HTTP server exposes /metrics endpoint for Prometheus scraping

Environment Variables:
    MODE                — Behavior mode (cpu|memory|rabbitmq|prometheus)
    LOAD_INTENSITY      — CPU load intensity 1-100 (default: 50)
    MEMORY_LIMIT_MB     — Memory limit per request in MB (default: 64)
    PROCESSING_DELAY_MS — Processing delay in ms (default: 100)
    SERVER_PORT         — HTTP server port (default: 8080)
    METRICS_PORT        — Metrics server port for prometheus mode (default: 8000)
    RABBITMQ_URL        — RabbitMQ connection URL (default: amqp://guest:guest@rabbitmq:5672)
    RABBITMQ_QUEUE      — RabbitMQ queue name (default: task-queue)
    RABBITMQ_ROLE       — RabbitMQ role: producer|consumer (default: consumer)
    CONFIG_FILE         — Optional path to configuration file (JSON)
"""

import os
import sys
import signal
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('workload')

# Valid modes
VALID_MODES = ('cpu', 'memory', 'rabbitmq', 'prometheus')

# Global state
request_count = 0
request_count_lock = threading.Lock()


def load_config_from_file(config_path):
    """Load configuration from a JSON file.

    Args:
        config_path: Path to JSON configuration file.

    Returns:
        dict: Configuration values from file.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        json.JSONDecodeError: If config file is invalid JSON.
    """
    logger.info(f"Loading configuration from file: {config_path}")
    with open(config_path, 'r') as f:
        return json.load(f)


def get_config():
    """Get configuration from environment variables and optional config file.

    Returns:
        dict: Complete configuration dictionary.
    """
    config = {
        'mode': os.environ.get('MODE', 'cpu').lower(),
        'load_intensity': int(os.environ.get('LOAD_INTENSITY', '50')),
        'memory_limit_mb': int(os.environ.get('MEMORY_LIMIT_MB', '64')),
        'processing_delay_ms': int(os.environ.get('PROCESSING_DELAY_MS', '100')),
        'server_port': int(os.environ.get('SERVER_PORT', '8080')),
        'metrics_port': int(os.environ.get('METRICS_PORT', '8000')),
        'rabbitmq_url': os.environ.get('RABBITMQ_URL', 'amqp://guest:guest@rabbitmq:5672'),
        'rabbitmq_queue': os.environ.get('RABBITMQ_QUEUE', 'task-queue'),
        'rabbitmq_role': os.environ.get('RABBITMQ_ROLE', 'consumer').lower(),
    }

    config_file = os.environ.get('CONFIG_FILE')
    if config_file and os.path.exists(config_file):
        try:
            file_config = load_config_from_file(config_file)
            config.update(file_config)
            logger.info("Configuration merged with file settings")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load config file {config_file}: {e}")

    return config


def log_startup_config(config):
    """Log the startup configuration for visibility."""
    logger.info("=" * 50)
    logger.info("Workload Configuration:")
    for key, value in sorted(config.items()):
        if 'password' in key.lower() or 'url' in key.lower():
            logger.info(f"  {key}: ****")
        else:
            logger.info(f"  {key}: {value}")
    logger.info("=" * 50)


def increment_request_count():
    """Thread-safe increment of request counter."""
    global request_count
    with request_count_lock:
        request_count += 1


def get_request_count():
    """Thread-safe read of request counter."""
    with request_count_lock:
        return request_count


class WorkloadHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler that routes requests to mode-specific handlers."""

    config = None
    cpu_handler = None
    memory_handler = None
    rabbitmq_handler = None
    prometheus_handler = None

    def log_message(self, format, *args):
        """Override to use our logger instead of stderr."""
        logger.debug(f"HTTP: {format % args}")

    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == '/health':
            self._send_json(200, {'status': 'ok', 'mode': self.config['mode']})

        elif path == '/stats':
            self._send_json(200, {
                'mode': self.config['mode'],
                'total_requests': get_request_count(),
                'load_intensity': self.config['load_intensity'],
                'memory_limit_mb': self.config['memory_limit_mb']
            })

        elif path == '/metrics' and self.config['mode'] == 'prometheus':
            self._handle_prometheus_metrics()

        else:
            self._send_json(404, {'error': 'Not found'})

    def do_POST(self):
        """Handle POST requests — main entry point for load generation."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)

        # Parse optional JSON body
        content_length = int(self.headers.get('Content-Length', 0))
        body = {}
        if content_length > 0:
            request_body = self.rfile.read(content_length)
            try:
                body = json.loads(request_body)
            except json.JSONDecodeError:
                pass

        mode = self.config['mode']

        if path == '/cpu' and mode == 'cpu':
            self._handle_cpu_request(query_params, body)

        elif path == '/memory' and mode == 'memory':
            self._handle_memory_request(query_params, body)

        elif path == '/produce' and mode == 'rabbitmq':
            self._handle_rabbitmq_produce(query_params, body)

        elif path == '/consume' and mode == 'rabbitmq':
            self._handle_rabbitmq_consume(query_params, body)

        else:
            self._send_json(400, {
                'error': 'Endpoint not available in current mode',
                'mode': mode,
                'path': path
            })

    def _handle_cpu_request(self, query_params, body):
        """Handle CPU load request — triggers CPU-intensive computation."""
        increment_request_count()

        # Get intensity from query params, body, or config
        intensity = self._get_param(query_params, body, 'intensity', self.config['load_intensity'])
        intensity = int(intensity)

        try:
            result = self.cpu_handler.execute(intensity)
            self._send_json(200, {
                'status': 'completed',
                'mode': 'cpu',
                'intensity': intensity,
                'computation_time_ms': result.get('computation_time_ms', 0),
                'operations': result.get('operations', 0)
            })
        except Exception as e:
            logger.error(f"CPU computation failed: {e}")
            self._send_json(500, {'error': str(e)})

    def _handle_memory_request(self, query_params, body):
        """Handle memory load request — triggers memory allocation."""
        increment_request_count()

        # Get memory limit from query params, body, or config
        memory_mb = self._get_param(query_params, body, 'memory_mb', self.config['memory_limit_mb'])
        memory_mb = int(memory_mb)

        try:
            result = self.memory_handler.allocate(memory_mb)
            self._send_json(200, {
                'status': 'completed',
                'mode': 'memory',
                'allocated_mb': result.get('allocated_mb', 0),
                'hold_time_ms': result.get('hold_time_ms', 0)
            })
        except Exception as e:
            logger.error(f"Memory allocation failed: {e}")
            self._send_json(500, {'error': str(e)})

    def _handle_rabbitmq_produce(self, query_params, body):
        """Handle RabbitMQ produce request."""
        increment_request_count()

        message_count = int(self._get_param(query_params, body, 'count', 10))
        message_size = int(self._get_param(query_params, body, 'size', 256))

        try:
            result = self.rabbitmq_handler.produce_messages(message_count, message_size)
            self._send_json(200, result)
        except Exception as e:
            logger.error(f"RabbitMQ produce failed: {e}")
            self._send_json(500, {'error': str(e)})

    def _handle_rabbitmq_consume(self, query_params, body):
        """Handle RabbitMQ consume request."""
        increment_request_count()

        message_count = int(self._get_param(query_params, body, 'count', 10))
        delay_ms = int(self._get_param(query_params, body, 'delay', self.config['processing_delay_ms']))

        try:
            result = self.rabbitmq_handler.consume_messages(message_count, delay_ms)
            self._send_json(200, result)
        except Exception as e:
            logger.error(f"RabbitMQ consume failed: {e}")
            self._send_json(500, {'error': str(e)})

    def _handle_prometheus_metrics(self):
        """Handle Prometheus metrics endpoint."""
        increment_request_count()

        # Record the request in Prometheus metrics to trigger KEDA scaling
        if self.prometheus_handler:
            self.prometheus_handler.record_request(mode='prometheus', computation_time=0.001)

        try:
            metrics_text = self.prometheus_handler.get_metrics_text()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()
            self.wfile.write(metrics_text.encode('utf-8'))
        except Exception as e:
            logger.error(f"Prometheus metrics failed: {e}")
            self._send_json(500, {'error': str(e)})

    def _get_param(self, query_params, body, key, default):
        """Get parameter from query params, body, or default."""
        if key in query_params:
            return query_params[key][0]
        if key in body:
            return body[key]
        return default

    def _send_json(self, status_code, data):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))


class GracefulHTTPServer(HTTPServer):
    """HTTP Server with graceful shutdown support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True

    def serve_forever(self, poll_interval=0.5):
        """Serve until running=False."""
        while self.running:
            self.handle_request()

    def shutdown_gracefully(self):
        """Set running flag and shutdown."""
        self.running = False
        self.shutdown()


def main():
    """Main entry point — start HTTP server with mode-specific handlers."""
    config = get_config()
    log_startup_config(config)

    mode = config['mode']

    if mode not in VALID_MODES:
        logger.error(f"Invalid MODE: '{mode}'. Must be one of: {', '.join(VALID_MODES)}")
        sys.exit(1)

    logger.info(f"Starting workload HTTP server in '{mode}' mode...")

    # Initialize mode-specific handlers
    if mode == 'cpu':
        from cpu_stress import CPUStress
        WorkloadHTTPHandler.cpu_handler = CPUStress()

    elif mode == 'memory':
        from memory_stress import MemoryStress
        WorkloadHTTPHandler.memory_handler = MemoryStress()

    elif mode == 'rabbitmq':
        from rabbitmq_worker import RabbitMQWorker
        WorkloadHTTPHandler.rabbitmq_handler = RabbitMQWorker(
            url=config['rabbitmq_url'],
            queue=config['rabbitmq_queue'],
            processing_delay_ms=config['processing_delay_ms']
        )

        # Start background consumer for auto-scaling with KEDA
        rabbitmq_role = os.environ.get('RABBITMQ_ROLE', 'consumer').lower()
        if rabbitmq_role == 'consumer':
            def auto_consume_loop():
                """Continuously consume messages for KEDA scaling."""
                logger.info("Starting background message consumer for KEDA scaling...")
                while True:
                    try:
                        result = WorkloadHTTPHandler.rabbitmq_handler.consume_messages(
                            count=10, delay_ms=config['processing_delay_ms']
                        )
                        consumed = result.get('consumed', 0)
                        if consumed > 0:
                            logger.info(f"Auto-consumed {consumed} messages")
                        else:
                            # No messages, wait before retry
                            time.sleep(1)
                    except Exception as e:
                        logger.error(f"Auto-consume error: {e}")
                        time.sleep(2)

            consumer_thread = threading.Thread(target=auto_consume_loop, daemon=True)
            consumer_thread.start()

    elif mode == 'prometheus':
        from metrics_server import MetricsHandler
        WorkloadHTTPHandler.prometheus_handler = MetricsHandler(
            load_intensity=config['load_intensity']
        )

    # Set config on handler class
    WorkloadHTTPHandler.config = config

    # Create and start HTTP server
    server_address = ('0.0.0.0', config['server_port'])
    httpd = GracefulHTTPServer(server_address, WorkloadHTTPHandler)

    # Set up signal handlers
    def handle_sigterm(signum, frame):
        logger.info(f"Received signal {signum}, shutting down HTTP server...")
        httpd.shutdown_gracefully()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    logger.info(f"HTTP server listening on port {config['server_port']}")
    logger.info(f"Endpoints: /health, /stats, /cpu (POST), /memory (POST)")

    try:
        httpd.serve_forever()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Workload HTTP server shut down gracefully")


if __name__ == '__main__':
    main()
