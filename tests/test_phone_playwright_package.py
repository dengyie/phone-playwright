import pathlib
import sys
import unittest

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PACKAGE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class PhonePlaywrightPackageTests(unittest.TestCase):
    def test_skill_manifest_structure(self):
        skill_md = PACKAGE_ROOT / "SKILL.md"
        self.assertTrue(skill_md.exists(), "SKILL.md 必须存在")
        content = skill_md.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"), "SKILL.md 必须包含 YAML frontmatter")
        self.assertIn("name: phone-playwright", content)
        self.assertIn("description:", content)
        self.assertIn("Triggers:", content)
        self.assertIn("references/architecture.md", content)
        self.assertIn("references/api-reference.md", content)
        self.assertIn("references/pitfalls.md", content)

    def test_scripts_exist_and_valid(self):
        scripts_dir = PACKAGE_ROOT / "scripts"
        cli_script = scripts_dir / "cli.py"
        inspect_script = scripts_dir / "inspect_ui.py"
        self.assertTrue(cli_script.exists(), "scripts/cli.py 必须存在")
        self.assertTrue(inspect_script.exists(), "scripts/inspect_ui.py 必须存在")

    def test_references_exist(self):
        ref_dir = PACKAGE_ROOT / "references"
        self.assertTrue((ref_dir / "architecture.md").exists())
        self.assertTrue((ref_dir / "api-reference.md").exists())
        self.assertTrue((ref_dir / "pitfalls.md").exists())

    def test_core_module_imports(self):
        from phone_playwright.api.async_api import AsyncPhonePlaywright
        from phone_playwright.api.sync_api import SyncPhonePlaywright
        from phone_playwright.core.state_machine import ActionabilityEngine
        from phone_playwright.core.pruner import SemanticPruner
        from phone_playwright.mcp.server import PhonePlaywrightMcpServer

        self.assertIsNotNone(AsyncPhonePlaywright)
        self.assertIsNotNone(SyncPhonePlaywright)
        self.assertIsNotNone(ActionabilityEngine)
        self.assertIsNotNone(SemanticPruner)
        self.assertIsNotNone(PhonePlaywrightMcpServer)


if __name__ == "__main__":
    unittest.main()
