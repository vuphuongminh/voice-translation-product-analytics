all: data analysis test

data:
	python src/generate_data.py

analysis:
	python src/analyze.py

test:
	python -m pytest -q

.PHONY: all data analysis test
