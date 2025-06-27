#!/usr/bin/env python3
"""
PondTV Launcher Script
Simple launcher for the PondTV application that handles imports properly.
"""

import sys
import os
import subprocess

def main():
    """Launch PondTV using the proper module structure."""
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Set the python path to include the 'src' directory
    python_path = os.path.join(script_dir, 'src')
    
    # Use subprocess to run the module properly
    try:
        # We now run `pondtv.main` from within the `src` directory
        result = subprocess.run(
            [sys.executable, '-m', 'pondtv.main'],
            cwd=python_path, # Run from the src directory
            check=True
        )
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running PondTV: {e}")
        return e.returncode
    except KeyboardInterrupt:
        print("\nPondTV interrupted by user")
        return 0

if __name__ == '__main__':
    sys.exit(main()) 