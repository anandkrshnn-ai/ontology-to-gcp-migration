from setuptools import setup, find_packages

setup(
    name="ontology_dataflow",
    version="0.1",
    install_requires=[
        "google-cloud-spanner",
        "pyyaml",
    ],
    packages=find_packages(),
)
