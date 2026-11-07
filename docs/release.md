# mattstack release guide

Cut a release by hand. No workflow publishes releases, so every release is
these six steps, run in order from a clean checkout of `main`.

## 1. Bump the version

Set `version` in `pyproject.toml` to the release version, then commit that
file.

```bash
git add pyproject.toml
git commit -m "chore(release): Bump version to X.Y.Z"
```

## 2. Run every gauntlet gate

Run the full gauntlet on a clean tree and require every gate to pass,
including gate 10 (INSTALL). Gate 10 builds the wheel from the sdist and
runs `mattstack --help` and `mattstack sync --help` in a fresh virtual
environment, so a dependency break fails the gate instead of the published
release.

```bash
make gauntlet
```

## 3. Tag the release

Tag the release commit and push the tag.

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## 4. Build the sdist, then the wheel from it

Check out the tag in a clean checkout, build the source distribution, then
build the wheel from that sdist. Both artifacts land in `dist/`.

```bash
git checkout vX.Y.Z
uv build --sdist
uv build --wheel dist/*.tar.gz
```

## 5. Smoke-test the wheel in a fresh environment

Install the wheel into a new `uv venv` created outside the repository, then
run the CLI's help commands. A missing dependency or entry point fails here.

```bash
uv venv /tmp/mattstack-release-venv
uv pip install --python /tmp/mattstack-release-venv/bin/python dist/*.whl
/tmp/mattstack-release-venv/bin/mattstack --help
/tmp/mattstack-release-venv/bin/mattstack sync --help
```

## 6. Publish the GitHub release

Attach both artifacts and let `gh` generate the release notes from the
commits since the previous tag.

```bash
gh release create vX.Y.Z dist/*.tar.gz dist/*.whl --generate-notes
```
