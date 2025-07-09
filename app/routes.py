"""
Flask Application Routes Module

This module defines the base application routes including the index and health check endpoints.
These routes provide basic service information and health monitoring capabilities,
which are useful for deployments and service discovery for both TTS and STT services.
"""

import time

from flask import Flask, jsonify


def register_routes(app: Flask) -> None:
    """
    Register basic application routes to the Flask app.

    Args:
        app (Flask): The Flask application instance.
    """

    @app.route("/")
    def index():
        """
        Root endpoint that returns basic service information.

        Returns:
            Response: JSON containing service status and version.
        """
        return jsonify(
            {
                "status": "ok",
                "service": "tts-stt-service",
                "version": app.config.get("VERSION", "0.1.0"),
                "endpoints": {
                    "tts": "/api/tts",
                    "stt": "/api/stt",
                    "stt_stream": "/api/stt/stream",
                    "health": "/health",
                },
            }
        )

    @app.route("/health")
    def health():
        """
        Health check endpoint for monitoring service health.

        Returns:
            Response: JSON containing health status and current timestamp.
        """
        return jsonify({"status": "healthy", "timestamp": time.time()})
