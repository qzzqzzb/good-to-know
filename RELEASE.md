# PyPI Release Checklist

This document is the maintainer checklist for cutting a formal `goodtoknow-gtn` release to PyPI.

## Current target

- Package: `goodtoknow-gtn`
- Version: `0.3.0`

## Pre-release checks

1. Confirm the working tree is clean except for intentional release-only changes.
2. Run the GTN local-product regression suite:

   ```bash
   python3 -m unittest discover -s tests/gtn_local_product -p 'test_*.py'
   ```

3. Confirm the Python modules compile:

   ```bash
   python3 -m compileall runtime/gtn_local_product tests/gtn_local_product
   ```

4. Build fresh distribution artifacts:

   ```bash
   uv build
   ```

5. Inspect wheel metadata and package contents:

   ```bash
   python3 - <<'PY'
   import pathlib, zipfile
   wheel = sorted(pathlib.Path("dist").glob("goodtoknow_gtn-*.whl"))[-1]
   print("wheel:", wheel)
   with zipfile.ZipFile(wheel) as zf:
       meta_name = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")][0]
       meta = zf.read(meta_name).decode("utf-8", errors="replace")
       for line in meta.splitlines():
           if line.startswith("Version: ") or line.startswith("Requires-Dist: "):
               print(line)
   PY
   ```

6. Do a clean install smoke test in a temporary environment:

   ```bash
   tmpdir=$(mktemp -d)
   uv venv "$tmpdir/.venv"
   uv pip install --python "$tmpdir/.venv/bin/python" dist/goodtoknow_gtn-0.3.0-py3-none-any.whl
   "$tmpdir/.venv/bin/gtn" --help
   ```

7. Do one install-gtn-style upgrade smoke test against a disposable `GTN_HOME`:

   ```bash
   export GTN_HOME="$(mktemp -d)"
   uv pip install --python "$GTN_HOME/.venv/bin/python" --upgrade --force-reinstall dist/goodtoknow_gtn-0.3.0-py3-none-any.whl
   env -u NO_COLOR gtn status
   ```

## Publish

If PyPI credentials are already configured:

```bash
uv publish
```

If you want to publish specific artifacts explicitly:

```bash
uv publish dist/goodtoknow_gtn-0.3.0.tar.gz dist/goodtoknow_gtn-0.3.0-py3-none-any.whl
```

## Post-publish smoke

1. Install from PyPI in a clean environment:

   ```bash
   tmpdir=$(mktemp -d)
   uv venv "$tmpdir/.venv"
   uv pip install --python "$tmpdir/.venv/bin/python" goodtoknow-gtn==0.3.0
   "$tmpdir/.venv/bin/gtn" --help
   ```

2. Validate the install path used by `install_gtn`:

   ```bash
   uv pip install --python ~/.gtn/.venv/bin/python --upgrade goodtoknow-gtn==0.3.0
   env -u NO_COLOR gtn status
   ```

3. Tag the release if you have not already:

   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```

## Notes

- If color does not show up in `gtn status`, check whether `NO_COLOR=1` is set in the shell environment.
- `Run dir` is expected to show `No run yet` until the first successful local run creates a run directory under `GTN_HOME/runs/`.
