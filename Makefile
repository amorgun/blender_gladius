.PHONY: all build validate
BLENDER := blender
TMP_DIR := build

all: build

build: __init__.py importer.py utils.py \
 LICENSE README.md blender_manifest.toml
	mkdir $(TMP_DIR); \
	cp --parents $^ $(TMP_DIR); \
	cd $(TMP_DIR); \
	$(BLENDER) --command extension build --verbose; \
	cd ..;
	cp $(TMP_DIR)/*.zip .; \
	rm -rf $(TMP_DIR)

validate:
	$(BLENDER) --command extension validate
