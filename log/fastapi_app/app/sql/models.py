# -*- coding: utf-8 -*-
"""Database models definitions. Table representations as class."""


from datetime import datetime
from influxdb_client import Point

class LogModel:
    """Log model for InfluxDB."""

    @staticmethod
    def create_point(exchange, routing_key, data, log_level="INFO"):
        """Create a log point for InfluxDB."""
        return Point("log") \
            .tag("exchange", exchange) \
            .tag("routing_key", routing_key) \
            .tag("log_level", log_level) \
            .field("message", data) \
            .time(datetime.utcnow().isoformat())