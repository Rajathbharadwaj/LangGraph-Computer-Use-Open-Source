"""
Monitoring and error tracking setup
"""
import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

def init_monitoring():
    """
    Initialize Sentry monitoring
    """
    sentry_dsn = os.getenv("SENTRY_DSN")
    environment = os.getenv("ENVIRONMENT", "development")
    
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            traces_sample_rate=1.0 if environment == "development" else 0.1,
            
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            profiles_sample_rate=1.0 if environment == "development" else 0.1,
        )
        print(f"✅ Sentry monitoring initialized for {environment}")
    else:
        print("⚠️  Sentry DSN not configured, monitoring disabled")


def capture_exception(error: Exception, context: dict = None):
    """
    Capture exception with context
    
    Args:
        error: Exception to capture
        context: Additional context
    """
    if context:
        sentry_sdk.set_context("custom", context)
    
    sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = "info"):
    """
    Capture custom message
    
    Args:
        message: Message to capture
        level: Log level (info, warning, error)
    """
    sentry_sdk.capture_message(message, level=level)

