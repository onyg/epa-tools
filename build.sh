#!/bin/bash

# Error handling: The script will terminate on error.
set -e

pip install shiv

shiv -c epatools -o dist/epatools.pyz -e epatools.main:main .