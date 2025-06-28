#!/usr/bin/env python3
"""
PondTV Launcher Script
Simple launcher for the PondTV application.
"""

import sys
import os

def main():
    """Launch PondTV using the proper module structure."""
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pondtv_dir = os.path.join(script_dir, 'pondtv')
    
    # Add pondtv directory to Python path
    sys.path.insert(0, pondtv_dir)
    
    # Import and run the main module
    try:
        from main import main as pondtv_main
        return pondtv_main()
    except ImportError as e:
        print(f"Error importing PondTV: {e}")
        return 1
    except KeyboardInterrupt:
        print("\nPondTV interrupted by user")
        return 0

if __name__ == '__main__':
    sys.exit(main()) 