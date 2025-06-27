#!/usr/bin/env python3
"""
PondTV Launcher Script
This script is the entry point for the PondTV application.
"""

import sys
import os

def main():
    """Launch PondTV using the proper module structure."""
    # This makes it possible to run the app from /opt/pondtv
    # and ensures that 'import pondtv.main' works correctly.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    try:
        from app import main as app_main
        return app_main.main()
    except Exception as e:
        # A simple logger in case the main app fails to import or run
        with open("/tmp/pondtv_launcher_error.log", "a") as f:
            f.write(f"Error running PondTV: {e}\n")
        return 1

if __name__ == '__main__':
    sys.exit(main()) 