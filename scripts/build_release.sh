#!/bin/bash

# PondTV Release Builder
# This script creates release packages for distribution

set -e

echo "🚀 Building PondTV Release Packages"
echo "==================================="

# Clean up any previous builds
rm -rf release/dist
mkdir -p release/dist

# Create boot payload package
echo "📦 Creating boot payload package..."
cd release
zip -r dist/pondtv-boot-payload.zip boot-payload/
cd ..

# Create source package
echo "📦 Creating source package..."
zip -r release/dist/pondtv-source.zip \
    pondtv/ \
    scripts/ \
    examples/ \
    run.py \
    requirements.txt \
    README.md \
    -x "*.pyc" "*__pycache__*" "*.DS_Store"

echo ""
echo "✅ Release packages created in release/dist/:"
ls -la release/dist/

echo ""
echo "📋 Release checklist:"
echo "   □ Test boot payload on fresh Pi"
echo "   □ Test one-command installer"
echo "   □ Update GitHub release with packages"
echo "   □ Update README with correct URLs" 