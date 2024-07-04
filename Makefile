SHELL := /bin/bash
POETRY := poetry

all: install test

install:
	# Install all dependencies
	$(POETRY) install -E all

install-qr-reader:
	# Install qr-reader dependencies only
	$(POETRY) install -E qr-reader

install-owlv2:
	# Install owlv2 dependencies only
	$(POETRY) install -E owlv2

install-zeroshot-counting:
	# Install loca dependencies only
	$(POETRY) install -E loca

test:
	# Run all unit tests
	$(POETRY) run pytest tests

serve/docs:
	# Start the documentation server
	$(POETRY) run mkdocs serve
