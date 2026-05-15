VERSION := $(shell cat VERSION)

module.tar.gz: run.sh requirements.txt meta.json src/*.py viam_visuals/*.py viam_visuals/_internal/*.py assets/*
	tar czf $@ $^

.PHONY: test
test:
	.venv/bin/pip install -q -r requirements-dev.txt
	.venv/bin/pytest

.PHONY: assets
assets:
	.venv/bin/python scripts/generate_assets.py

.PHONY: upload
upload: test module.tar.gz
	viam module upload --version=$(VERSION) --platform=linux/any module.tar.gz
