"""
Flask Application Factory Module for TTS-Engine.
"""

import os
from typing import Type
from flask import Flask

from adapters.clients.google_tts_client import GoogleTTSClient
from adapters.clients.google_stt_client import GoogleSTTClient
from adapters.clients.google_stt_streaming_client import GoogleSTTStreamingClient
from adapters.controllers.tts_controller import create_tts_blueprint
from adapters.controllers.stt_controller import create_stt_blueprint
from adapters.controllers.stt_streaming_controller import create_stt_streaming_blueprint
from adapters.loggers.logger_adapter import app_logger
from app.extensions import register_extensions, socketio
from app.handlers import (
    register_error_handlers,
    register_request_hooks,
    register_shutdown_handlers,
)
from app.routes import register_routes
from config import Config, DevelopmentConfig, ProductionConfig
from usecases.synthesize_speech_use_case import SynthesizeSpeechUseCase
from usecases.transcribe_speech_use_case import TranscribeSpeechUseCase
from core.services.tts_domain_service import TTSDomainService
from core.services.stt_domain_service import STTDomainService
from core.services.stt_streaming_domain_service import STTStreamingDomainService


class ApplicationFactory:  
    """
    Factory class for creating and configuring Flask application instances.

    This class provides static methods to create a properly configured Flask
    application with all necessary extensions, blueprints, and use cases registered.
    """

    @staticmethod
    def create_app(config_class: Type[Config] = None) -> Flask:
        """
        Create and configure a Flask application instance.

        Args:
            config_class: Configuration class to use. If None, will be determined
                         based on FLASK_ENV environment variable.

        Returns:
            Flask: Configured Flask application instance.
        """
        if config_class is None:
            env = os.environ.get("FLASK_ENV", "development").lower()
            cfg_map = {
                "development": DevelopmentConfig,
                "production": ProductionConfig,
            }
            config_class = cfg_map.get(env, DevelopmentConfig)

        flask_app = Flask(__name__)
        flask_app.config.from_object(config_class)

        register_extensions(flask_app)
        ApplicationFactory._register_use_cases(flask_app)
        ApplicationFactory._register_blueprints(flask_app)
        register_error_handlers(flask_app)
        register_request_hooks(flask_app)
        register_shutdown_handlers(flask_app)
        register_routes(flask_app)

        app_logger.info(
            "TTS-Engine started in %s mode", os.environ.get("FLASK_ENV", "development")
        )
        return flask_app

    @staticmethod
    def _register_use_cases(flask_app):
        """Register use cases and dependencies with the Flask application."""
        
        google_tts_client = GoogleTTSClient()
        tts_service = TTSDomainService(google_tts_client)
        flask_app.synthesize_speech_use_case = SynthesizeSpeechUseCase(tts_service)

        
        google_stt_client = GoogleSTTClient()
        stt_service = STTDomainService(google_stt_client)
        flask_app.transcribe_speech_use_case = TranscribeSpeechUseCase(stt_service)

        # STT Streaming
        google_stt_streaming_client = GoogleSTTStreamingClient()
        stt_streaming_service = STTStreamingDomainService(google_stt_streaming_client, app_logger)
        flask_app.stt_streaming_service = stt_streaming_service

    @staticmethod
    def _register_blueprints(flask_app):
        """Register blueprints with the Flask application."""
        
        tts_blueprint = create_tts_blueprint(flask_app.synthesize_speech_use_case)
        flask_app.register_blueprint(tts_blueprint)

        
        stt_blueprint = create_stt_blueprint(flask_app.transcribe_speech_use_case)
        flask_app.register_blueprint(stt_blueprint)

        # STT Streaming Blueprint
        stt_streaming_blueprint = create_stt_streaming_blueprint(flask_app.stt_streaming_service)
        flask_app.register_blueprint(stt_streaming_blueprint)
        
        # Register SocketIO events
        if hasattr(stt_streaming_blueprint, 'streaming_controller'):
            stt_streaming_blueprint.streaming_controller.register_events(socketio)


create_app = ApplicationFactory.create_app
app = create_app()

# Export SocketIO instance for running with socketio
socketio_app = socketio

if __name__ == "__main__":
    # Run with SocketIO support
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    app.run(
        host=app.config.get("HOST", "0.0.0.0"),
        port=app.config.get("PORT", 5003),
        debug=app.config.get("DEBUG", False),
    )
