from setuptools import setup, find_packages

setup(
    name="ontology_dataflow",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "google-cloud-spanner",
        "pyyaml",
    ],
)
