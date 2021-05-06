from pathlib import Path

from setuptools import setup


with open(Path(__file__).parent / "README.md", "r") as f:
    README = f.read()


setup(
    name="py-nestedtext",
    version="0.0.3",
    description="Minimal implementation of NestedText data format",
    long_description=README,
    author="Lewis Gaul",
    author_email="lewis.gaul@gmail.com",
    license="MIT",
    package_dir={"": "src"},
    py_modules=["nestedtext"],
    scripts=["src/nt-cli"],
    install_requires=[],
    python_requires=">=3.6",
    keywords=["data"],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Text Processing :: Markup",
        "Topic :: Utilities",
    ],
)
