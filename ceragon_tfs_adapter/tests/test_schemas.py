"""
Unit tests for the bundled Ceragon YANG schemas accessor.
"""

import unittest
from ceragon_tfs_adapter.schemas import (
    list_schemas,
    get_schema_path,
    get_schema_content,
    get_all_schemas,
    SCHEMAS_DIR,
)


class TestCeragonSchemas(unittest.TestCase):

    def test_schemas_directory_exists(self):
        self.assertTrue(SCHEMAS_DIR.exists())
        self.assertTrue(SCHEMAS_DIR.is_dir())

    def test_list_schemas(self):
        schemas = list_schemas()
        self.assertGreaterEqual(len(schemas), 51)
        self.assertIn("radio-bridge-tg-user-bridge", schemas)
        self.assertIn("radio-bridge-tg-radio-common", schemas)
        self.assertIn("radio-bridge-tg-interfaces", schemas)
        self.assertIn("ietf-yang-library", schemas)

    def test_get_schema_content(self):
        content = get_schema_content("radio-bridge-tg-user-bridge")
        self.assertIsNotNone(content)
        self.assertIn("module radio-bridge-tg-user-bridge", content)
        self.assertIn("namespace \"http://siklu.com/yang/tg/user-bridge\"", content)

    def test_get_nonexistent_schema(self):
        path = get_schema_path("non-existent-module-xyz")
        self.assertIsNone(path)
        content = get_schema_content("non-existent-module-xyz")
        self.assertIsNone(content)

    def test_get_all_schemas(self):
        all_schemas = get_all_schemas()
        self.assertGreaterEqual(len(all_schemas), 51)
        self.assertIn("radio-bridge-tg-system", all_schemas)


if __name__ == "__main__":
    unittest.main()
