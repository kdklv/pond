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
    pondtv_dir = os.path.join(script_dir, 'pondtv')
    
    # Change to the pondtv directory and run the main module
    os.chdir(pondtv_dir)
    
    # Use subprocess to run the module properly
    try:
        result = subprocess.run([sys.executable, '-m', 'src.main'], check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running PondTV: {e}")
        return e.returncode
    except KeyboardInterrupt:
        print("\nPondTV interrupted by user")
        return 0

if __name__ == '__main__':
    sys.exit(main()) 