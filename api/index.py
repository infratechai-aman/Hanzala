"""Vercel Serverless Function entrypoint."""
import os
import sys

# Ensure repository root is on sys.path so app and config can be imported
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from run import app

# Export app for Vercel WSGI
__all__ = ["app"]
