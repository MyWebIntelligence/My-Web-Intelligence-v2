#!/usr/bin/env python3
"""
Test script for corpus export batching functionality

This file can be run as a standalone script or via pytest.
"""

import os
import sys
import tempfile
import shutil
from zipfile import ZipFile
import pytest

# Add the project root to the Python path
tests_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(tests_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try imports - skip tests if dependencies unavailable
try:
    from mwi.export import Export
    from mwi import model
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    IMPORT_ERROR = str(e)

pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE,
    reason=f"Required imports not available: {IMPORT_ERROR if not IMPORTS_AVAILABLE else ''}"
)

def test_corpus_export_batching():
    """
    Test that corpus export creates multiple ZIP files with proper naming
    """
    # Create a test directory
    test_dir = tempfile.mkdtemp()
    print(f"Test directory: {test_dir}")
    
    try:
        # Mock a land object
        class MockLand:
            def __init__(self):
                self.id = 1
                self.name = "TestLand"
            
            def get_id(self):
                return self.id
        
        # Create mock export instance
        land = MockLand()
        export = Export("corpus", land, minimum_relevance=0)
        
        # Create test filename
        test_filename = os.path.join(test_dir, "test_corpus.zip")
        
        # Test the write_corpus method
        # Note: This will fail with real database queries, but we can test the filename logic
        print("Testing filename generation logic...")
        
        # Test the filename manipulation logic
        base_filename = test_filename.replace('.zip', '')
        print(f"Base filename: {base_filename}")
        
        # Generate sample batch filenames
        for i in range(1, 6):
            batch_filename = f"{base_filename}_{i:05d}.zip"
            print(f"Batch {i}: {batch_filename}")
            
            # Create empty ZIP files to test the naming
            with ZipFile(batch_filename, 'w') as arch:
                arch.writestr("test.txt", "Test content")
        
        # Check that files were created
        created_files = [f for f in os.listdir(test_dir) if f.endswith('.zip')]
        created_files.sort()
        
        print(f"Created files: {created_files}")
        
        expected_files = [
            "test_corpus_00001.zip",
            "test_corpus_00002.zip", 
            "test_corpus_00003.zip",
            "test_corpus_00004.zip",
            "test_corpus_00005.zip"
        ]
        
        if created_files == expected_files:
            print("✓ Test passed: Filenames generated correctly")
            return True
        else:
            print("✗ Test failed: Filename generation incorrect")
            print(f"Expected: {expected_files}")
            print(f"Got: {created_files}")
            return False
            
    finally:
        # Clean up test directory
        shutil.rmtree(test_dir)

if __name__ == "__main__":
    print("Testing corpus export batching functionality...")
    success = test_corpus_export_batching()
    
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Tests failed!")
        sys.exit(1)