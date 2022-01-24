.DEFAULT_GOAL := help

define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

.PHONY: clean, coverage, diff_cover, docs, help, dev_requirements, test, test_quality, test_requirements, upgrade,\
		check_keywords

help: ## Display this help message
	@echo "Please use \`make <target>' where <target> is one of"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

clean: ## Remove generated byte code, coverage reports, and build artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	coverage erase
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

docs: ## generate Sphinx HTML documentation
	python setup.py build_sphinx

dev_requirements: ## Install Dev Requirements
	pip install -qr requirements/pip.txt
	pip install -r requirements/dev.txt

test_requirements: ## Install Test Requirements
	pip install -r requirements/test.txt

upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: ## Update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	pip-compile --upgrade --allow-unsafe --rebuild -o requirements/pip.txt requirements/pip.in
	pip-compile --upgrade --verbose --rebuild -o requirements/pip-tools.txt requirements/pip-tools.in
	pip-compile --upgrade --verbose --rebuild -o requirements/base.txt requirements/base.in
	pip-compile --upgrade --verbose --rebuild -o requirements/docs.txt requirements/docs.in
	pip-compile --upgrade --verbose --rebuild -o requirements/test.txt requirements/test.in
	pip-compile --upgrade --verbose --rebuild -o requirements/dev.txt requirements/dev.in
	pip-compile --upgrade --verbose --rebuild -o requirements/tox.txt requirements/tox.in
	pip-compile --upgrade --verbose --rebuild -o requirements/ci.txt requirements/ci.in
	# Let tox control the Django and DRF versions for tests
	sed -i.tmp '/^django==/d' requirements/test.txt
	sed -i.tmp '/^djangorestframework==/d' requirements/test.txt
	rm requirements/test.txt.tmp

test: clean ## Run tests in the current virtualenv
	pytest

coverage: clean ## Generate and view HTML coverage report
	py.test --cov-report html
	$(BROWSER) htmlcov/index.html

diff_cover: test ## Generate diff coverage report
	diff-cover coverage.xml

test_quality: ## Run Quality checks
	pylint submissions
	isort --check-only submissions manage.py setup.py settings.py
	pycodestyle . --config=pycodestyle

check_keywords: ## Scan the Django models in all installed apps in this project for restricted field names
	python manage.py check_reserved_keywords --override_file db_keyword_overrides.yml

##################
#Devstack commands
##################

install-local-submissions: ## installs your local submissions code into the LMS and Studio python virtualenvs
	docker exec -t edx.devstack.lms bash -c '. /edx/app/edxapp/venvs/edxapp/bin/activate && cd /edx/app/edxapp/edx-platform && pip uninstall -y edx-submissions && pip install -e /edx/src/edx-submissions && pip freeze | grep edx-submissions'
	docker exec -t edx.devstack.studio bash -c '. /edx/app/edxapp/venvs/edxapp/bin/activate && cd /edx/app/edxapp/edx-platform && pip uninstall -y edx-submissions && pip install -e /edx/src/edx-submissions && pip freeze | grep edx-submissions'
