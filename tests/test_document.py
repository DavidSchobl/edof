# tests/test_document.py
import io, pytest
import edof
from edof import Document, TextBox, Shape, QRCode


def test_create_document():
    doc = edof.new(title="Test", author="Tester")
    assert doc.title  == "Test"
    assert doc.author == "Tester"
    assert len(doc.pages) == 0


def test_add_page():
    doc  = edof.new()
    page = doc.add_page()
    assert len(doc.pages) == 1
    assert page.width  == doc.default_width
    assert page.height == doc.default_height


def test_add_textbox():
    doc  = edof.new()
    page = doc.add_page()
    tb   = page.add_textbox(10, 20, 80, 15, "Hello")
    assert tb.text == "Hello"
    assert isinstance(tb, TextBox)
    assert tb.transform.x == pytest.approx(10.0)
    assert tb.transform.y == pytest.approx(20.0)


def test_add_shape():
    doc  = edof.new()
    page = doc.add_page()
    sh   = page.add_shape("rect", 5, 5, 40, 20)
    assert isinstance(sh, Shape)
    assert sh.shape_type == "rect"


def test_add_qrcode():
    doc  = edof.new()
    page = doc.add_page()
    qr   = page.add_qrcode("https://example.com", 0, 0, 30)
    assert isinstance(qr, QRCode)
    assert qr.data == "https://example.com"


def test_variables():
    doc = edof.new()
    doc.define_variable("name", type="text", default="World")
    doc.set_variable("name", "Jan")
    assert doc.variables.get("name") == "Jan"


def test_fill_variables():
    doc = edof.new()
    doc.define_variable("a")
    doc.define_variable("b")
    doc.fill_variables({"a": "hello", "b": "world"})
    assert doc.variables.get("a") == "hello"
    assert doc.variables.get("b") == "world"


def test_save_load(tmp_path):
    doc  = edof.new(title="SaveTest")
    page = doc.add_page()
    page.add_textbox(0, 0, 50, 10, "Saved text")
    doc.define_variable("x", default="42")

    path = str(tmp_path / "test.edof")
    doc.save(path)

    doc2 = edof.load(path)
    assert doc2.title == "SaveTest"
    assert len(doc2.pages) == 1
    assert doc2.pages[0].objects[0].text == "Saved text"
    assert doc2.variables.get("x") == "42"


def test_validate_missing_variable():
    doc  = edof.new()
    page = doc.add_page()
    tb   = page.add_textbox(0, 0, 50, 10, "X")
    tb.variable = "nonexistent_var"
    issues = doc.validate()
    assert any("nonexistent_var" in i for i in issues)


def test_resource_embedding(tmp_path):
    from PIL import Image
    img_path = str(tmp_path / "img.png")
    Image.new("RGB", (10, 10), (255, 0, 0)).save(img_path)

    doc  = edof.new()
    rid  = doc.add_resource_from_file(img_path)
    page = doc.add_page()
    ib   = page.add_image(rid, 0, 0, 30, 30)
    assert ib.resource_id == rid
    assert rid in doc.resources


def test_serializer_peek(tmp_path):
    from edof.format.serializer import EdofSerializer
    doc = edof.new(title="Peek")
    doc.add_page()
    path = str(tmp_path / "peek.edof")
    doc.save(path)
    manifest = EdofSerializer.peek(path)
    assert manifest["title"] == "Peek"
    assert "edof_version" in manifest
