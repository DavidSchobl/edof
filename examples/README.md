# edof examples

Runnable, self-contained scripts. Each writes its output into `./out/`.

```bash
pip install edof[all]
python 01_hello_document.py
```

| Script | Shows |
|---|---|
| `01_hello_document.py` | Document → styled text → PNG + PDF |
| `02_table_and_rich_text.py` | Tables, mixed-style text runs |
| `03_vector_gradients.py` | Rects, ellipses, SVG-style paths, gradient fills |
| `04_layer_effects.py` | Long shadow (linear / constant / custom gradients), stroke |
| `05_variables_template.py` | Variables: one template, many renders |
| `06_save_load_roundtrip.py` | `.edof` save / load round-trip |

More task-oriented walkthroughs live in [docs/cookbook](../docs/cookbook/).
