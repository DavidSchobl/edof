# Changelog

## [3.0.0] – 2025-01-01

### Added
- Initial release of EDOF (Easy Document Format) 3.0
- ZIP-based `.edof` file format with JSON structure
- Full document model: Document, Page, ResourceStore
- Object types: TextBox, ImageBox, Shape, QRCode, Group
- TextStyle with auto-shrink (binary search for best font size)
- Named variable system with batch fill support
- Embedded resources (fonts, images)
- Transform system: translate, resize_uniform, resize_free, rotate, flip
- Colour-space support: RGB, RGBA, L (grayscale), 1 (B&W), CMYK
- Bit-depth support: 8-bit and 16-bit
- Pillow-based page renderer
- Bitmap export (PNG, JPEG, TIFF, BMP)
- PDF export (via reportlab, optional)
- Print support (Windows, macOS, Linux)
- QR code generation (via qrcode, optional)
- Tkinter canvas widget (EdofTkCanvas)
- PyQt6 widget (EdofQtWidget)
- Command API with undo/redo history stack
- Backward-compatibility system with migration layer
- Version warning when loading newer-format files (non-fatal)
- EDOF Editor desktop application (edof_editor.py)
- Full pytest test suite
- Type hints throughout (py.typed marker)
