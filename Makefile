.PHONY: install lint test validate demo report clean

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check flowtest tests

test:
	pytest --cov=flowtest --cov-report=term-missing

validate:
	flowtest validate testcases

demo:
	flowtest demo --parallel 3

report:
	flowtest demo --parallel 3 --report report.html

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist *.egg-info report.html
