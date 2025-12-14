#!/bin/bash

# Remove preprocessing directory with wrong documents
echo "Removing old preprocessing directory..."
rm -rf preprocess_squid/

# Remove only SQUiD query results (not other systems)
echo "Removing only SQUiD query results..."
find results/challenging_queries -type d -name "squid" -exec rm -rf {} + 2>/dev/null || true

echo "Cleanup complete!"
echo "You can now run: python preprocess_squid_data.py --dataset all"

