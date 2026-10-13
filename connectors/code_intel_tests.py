"""Regression tests for Cursor-style code intelligence bundled into the Android agent."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import code_intel


class OutlineTests(unittest.TestCase):
    def test_python_outline_includes_nested_classes_and_methods(self):
        source = '''\
def outer():
    class Inner:
        async def run(self):
            return True
'''
        self.assertEqual(
            code_intel.outline("sample.py", source),
            [(1, "def", "outer"), (2, "class", "outer.Inner"), (3, "def", "outer.Inner.run")],
        )

    def test_invalid_python_returns_no_partial_outline(self):
        self.assertEqual(code_intel.outline("broken.py", "def valid():\n  return 1\n def broken(:\n"), [])

    def test_javascript_outline_finds_functions_classes_and_arrow_functions(self):
        source = '''\
export async function loadData() {}
export class Workspace {}
const render = (value) => value;
interface ProjectInfo { name: string }
type ProjectId = string;
'''
        self.assertEqual(
            code_intel.outline("sample.ts", source),
            [
                (1, "def", "loadData"),
                (2, "class", "Workspace"),
                (3, "def", "render"),
                (4, "class", "ProjectInfo"),
                (5, "class", "ProjectId"),
            ],
        )

    def test_generic_outline_handles_java_declarations(self):
        source = "public class Project {\n  public void build() {}\n}\n"
        self.assertEqual(
            code_intel.outline("Project.java", source),
            [(1, "class", "Project"), (2, "def", "build")],
        )


class ProjectScanTests(unittest.TestCase):
    def test_project_scan_skips_hidden_and_dependency_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("pass\n")
            (root / ".git").mkdir()
            (root / ".git" / "history.py").write_text("pass\n")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "vendor.py").write_text("pass\n")
            found = {Path(p).relative_to(root).as_posix() for p in code_intel._project_files(str(root), {".py"})}
            self.assertEqual(found, {"src/main.py"})

    def test_project_scan_stops_after_file_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(code_intel.MAX_FILES + 2):
                (root / ("f%04d.py" % i)).touch()
            found = list(code_intel._project_files(str(root), {".py"}))
            self.assertEqual(len(found), code_intel.MAX_FILES)

    def test_shell_diagnostics_reports_real_syntax_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.sh"
            path.write_text("if then\n")
            problems = code_intel.extra_problems(str(path), tmp, deep=True)
            self.assertTrue(problems, "bash -n should report the malformed shell syntax")

    def test_missing_external_linter_is_not_reported_as_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "valid.py"
            path.write_text("def hello():\n    return 'hello'\n")
            with patch.object(code_intel.shutil, "which", return_value=None):
                self.assertEqual(code_intel.extra_problems(str(path), tmp, deep=True), [])


if __name__ == "__main__":
    unittest.main()
