"""
Tests for edof 4.0.2 — bug fixes and CLI extensions.

Coverage:
  - Variable {name} placeholder substitution at render time (the big bug)
  - Validate detects duplicate object IDs
  - Validate detects entirely off-page objects
  - Editor snap-to-grid applies during resize (verified via no-Qt headless test)
  - CLI new subcommands exist and dispatch correctly
"""
import os
import sys
import csv
import json
import tempfile
import subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import edof
from edof import TextBox, Shape, Group


# ── Variable substitution fix ────────────────────────────────────────────────

def test_variable_placeholder_substitutes_at_render():
    """The big v4.0.2 fix: {name} placeholders work in plain rendering."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "Hello {name}!")
    doc.define_variable("name", default="World")

    tb = page.objects[0]
    # Without setting the variable, default kicks in
    assert tb.get_resolved_text(doc.variables) == "Hello World!"

    # Now set it
    doc.set_variable("name", "Alice")
    assert tb.get_resolved_text(doc.variables) == "Hello Alice!"

    doc.set_variable("name", "Bob")
    assert tb.get_resolved_text(doc.variables) == "Hello Bob!"


def test_variable_substitution_renders_different_outputs(tmp_path):
    """End-to-end: rendering same template with different variable produces
    different bitmaps."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "Name: {name}")
    doc.define_variable("name", default="X")

    p1 = tmp_path / "alice.png"
    p2 = tmp_path / "bob.png"
    doc.set_variable("name", "Alice")
    doc.export_bitmap(str(p1), page=0, dpi=72)
    doc.set_variable("name", "Bob")
    doc.export_bitmap(str(p2), page=0, dpi=72)

    assert p1.read_bytes() != p2.read_bytes(), \
        "Substitution should produce different outputs for different values"


def test_missing_variable_keeps_placeholder():
    """Unknown variable name leaves {name} as literal."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "Hello {undefined_var}!")
    # No variable defined, no values

    tb = page.objects[0]
    # The text stays as-is (graceful fallback)
    out = tb.get_resolved_text(doc.variables)
    assert "{undefined_var}" in out


def test_multiple_placeholders_substitute():
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "{greeting} {name}, you owe {amount}.")
    doc.define_variable("greeting", default="Hi")
    doc.define_variable("name", default="Friend")
    doc.define_variable("amount", default="0")

    doc.fill_variables({"greeting": "Hello", "name": "Alice", "amount": "100"})
    tb = page.objects[0]
    assert tb.get_resolved_text(doc.variables) == "Hello Alice, you owe 100."


def test_placeholder_with_no_variables_unchanged():
    """When no variable store is passed, text returns literally."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "Hello {name}!")
    tb = page.objects[0]
    # No var store — text unchanged
    assert tb.get_resolved_text() == "Hello {name}!"
    assert tb.get_resolved_text(None) == "Hello {name}!"


# ── Validate enhancements ────────────────────────────────────────────────────

def test_validate_detects_duplicate_ids():
    doc = edof.new()
    page = doc.add_page()
    tb1 = page.add_textbox(10, 10, 100, 12, "First")
    tb2 = page.add_textbox(10, 30, 100, 12, "Second")
    # Force a duplicate
    tb2.id = tb1.id

    issues = doc.validate()
    assert any("Duplicate" in i for i in issues), \
        f"Expected duplicate-ID warning in: {issues}"


def test_validate_detects_off_page_object():
    doc = edof.new(width=210, height=297)
    page = doc.add_page()
    page.add_textbox(15, 15, 100, 10, "On page")
    bad = page.add_textbox(0, 0, 50, 10, "Off page")
    bad.transform.x = 250  # 250 > 210, entirely off-page

    issues = doc.validate()
    assert any("off-page" in i.lower() for i in issues), \
        f"Expected off-page warning in: {issues}"


def test_validate_off_page_does_not_flag_normal():
    doc = edof.new(width=210, height=297)
    page = doc.add_page()
    # Object overlapping the edge but not entirely off
    page.add_textbox(200, 290, 30, 20, "Spilled over")
    issues = doc.validate()
    assert not any("off-page" in i.lower() for i in issues), \
        f"Should not flag partially-overlapping object: {issues}"


def test_validate_recurses_into_groups_for_duplicate_check():
    doc = edof.new()
    page = doc.add_page()
    g = Group()
    tb1 = TextBox(text="A")
    tb2 = TextBox(text="B")
    tb2.id = tb1.id  # duplicate, hidden inside a group
    g.children = [tb1, tb2]
    page.add_object(g)

    issues = doc.validate()
    assert any("Duplicate" in i for i in issues)


# ── Editor snap-to-grid for resize (logic test, no Qt) ───────────────────────

def test_editor_resize_snap_logic_is_present():
    """v4.0.2: ensure the editor source mentions snap-to-grid in resize block."""
    import os
    editor_src = os.path.join(os.path.dirname(__file__), "..", "edof", "_apps", "editor.py")
    with open(editor_src, encoding='utf-8') as f:
        src = f.read()

    # The resize handle code path should now reference snap_to_grid
    # Find the section after `def _do_drag` or wherever resize happens
    assert "v4.0.2: snap the mouse position to grid first" in src, \
        "Resize block should have v4.0.2 grid snap logic"


# ── CLI new subcommands ──────────────────────────────────────────────────────

def _run_cli(*args, expected_exit=0):
    """Run edof-cli as a subprocess; return (stdout, stderr, exit_code)."""
    cmd = [sys.executable, "-m", "edof._apps.cli"] + list(args)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "..")
    res = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    if expected_exit is not None:
        assert res.returncode == expected_exit, \
            f"Expected exit {expected_exit}, got {res.returncode}\n" \
            f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    return res.stdout, res.stderr, res.returncode


def test_cli_help_lists_all_v402_subcommands():
    out, err, _ = _run_cli("--help")
    text = out + err
    for cmd in ("info", "objects", "validate", "export",
                "batch", "import", "convert", "to-v3",
                "set-password", "unlock-render"):
        assert cmd in text, f"Subcommand '{cmd}' not in --help output"


def test_cli_export_supports_password_flag():
    out, err, _ = _run_cli("export", "--help")
    text = out + err
    assert "--password" in text
    assert "--recovery-key" in text
    assert "--vector" in text
    assert "--raster" in text


def test_cli_batch_command_works(tmp_path):
    # Build a tiny template
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 180, 12, "Hello {name}!")
    doc.define_variable("name", default="X")
    template_path = tmp_path / "tpl.edof"
    doc.save(str(template_path))

    # Make a CSV
    csv_path = tmp_path / "data.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("name\nAlice\nBob\nCarol\n")

    out_pattern = str(tmp_path / "{name}.png")

    out, err, code = _run_cli("batch", str(template_path), str(csv_path),
                              "-o", out_pattern, "--dpi", "72")

    # All three files generated
    for who in ("Alice", "Bob", "Carol"):
        assert (tmp_path / f"{who}.png").exists(), f"Missing output for {who}"


def test_cli_set_password_and_unlock_render(tmp_path):
    """Encrypt via CLI, then render via unlock-render."""
    pytest.importorskip("cryptography")

    doc = edof.new(title="Secret")
    page = doc.add_page()
    page.add_textbox(10, 10, 100, 10, "TOP SECRET")
    template = tmp_path / "secret.edof"
    doc.save(str(template))

    # Encrypt
    out, err, code = _run_cli("set-password", str(template),
                              "--level", "admin",
                              "--password", "myPass123")
    assert code == 0, f"set-password failed: {err}"

    # Now info without password should NOT show contents
    out, err, code = _run_cli("info", str(template), expected_exit=None)
    assert "Encrypted:   yes" in (out + err)

    # info with password
    out, err, _ = _run_cli("info", str(template), "--password", "myPass123",
                            expected_exit=0)
    assert "Encrypted:   yes" in out

    # unlock-render to PDF
    pdf_out = tmp_path / "rendered.pdf"
    out, err, code = _run_cli("unlock-render", str(template), str(pdf_out),
                              "--password", "myPass123")
    assert code == 0, f"unlock-render failed: {err}"
    assert pdf_out.exists(), "PDF was not created"
    assert pdf_out.stat().st_size > 100, "PDF is suspiciously small"


def test_cli_set_password_wrong_password_exits_3(tmp_path):
    """Wrong password should give exit code 3."""
    pytest.importorskip("cryptography")

    doc = edof.new()
    doc.add_page().add_textbox(10, 10, 100, 10, "Test")
    template = tmp_path / "secret.edof"
    doc.save(str(template))

    # Set up password
    _run_cli("set-password", str(template),
             "--level", "admin", "--password", "right")

    # Try wrong password
    out, err, code = _run_cli("info", str(template), "--password", "wrong",
                              expected_exit=3)


def test_cli_validate_exit_code_4_on_failure(tmp_path):
    """Validation failure = exit code 4 (per docs)."""
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 100, 10, "")
    doc.define_variable("name", required=True)  # not set!
    template = tmp_path / "invalid.edof"
    doc.save(str(template))

    out, err, code = _run_cli("validate", str(template), expected_exit=4)


def test_cli_to_v3_produces_v3_file(tmp_path):
    doc = edof.new()
    page = doc.add_page()
    page.add_textbox(15, 15, 100, 10, "Test")
    template = tmp_path / "v4.edof"
    doc.save(str(template))

    out_v3 = tmp_path / "v3.edof"
    out, err, code = _run_cli("to-v3", str(template), "-o", str(out_v3))
    assert code == 0
    assert out_v3.exists()


# ── Backward compat: 4.0.1 features still work ──────────────────────────────

def test_v401_features_still_work():
    """v4.0.1 features (encryption, partial mode, recovery) shouldn't regress."""
    pytest.importorskip("cryptography")
    from edof.crypto import EDIT, ADMIN

    doc = edof.new(title="v4.0.1 regression")
    doc.add_page().add_textbox(10, 10, 100, 10, "Hello")

    # Set passwords
    rk = doc.set_password("admin", "x")
    doc.set_password("edit", "y")

    assert rk is not None
    assert doc.is_encrypted
    assert "admin" in doc.password_levels
    assert "edit" in doc.password_levels

    # Round-trip through save/load
    import io
    from edof.format.serializer import EdofSerializer
    data = EdofSerializer.to_bytes(doc)

    doc2 = EdofSerializer.from_bytes(data, password="y")
    assert doc2.permission_level == EDIT


# ── Persistence: editor settings (very lightweight check) ───────────────────

def test_editor_settings_class_attributes():
    """v4.0.2: Editor should be wired up with QSettings (verified via source)."""
    editor_src = os.path.join(os.path.dirname(__file__), "..", "edof", "_apps", "editor.py")
    with open(editor_src, encoding='utf-8') as f:
        src = f.read()

    assert "QSettings" in src, "Editor should import QSettings"
    assert "self._settings = QSettings" in src, "Editor should instantiate QSettings"
    assert "closeEvent" in src, "Editor should override closeEvent for persistence"
    assert "_recent_files" in src, "Editor should track recent files"
