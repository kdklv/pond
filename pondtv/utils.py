import logging
import sys

def setup_logger():
    """Set up the root logger for the application."""
    logger = logging.getLogger("pondtv")
    logger.setLevel(logging.INFO)

    # Create a handler to print to console
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Create a formatter and add it to the handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(handler)

    return logger

# Create a logger instance to be imported by other modules
log = setup_logger() 