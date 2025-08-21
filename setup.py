from setuptools import setup, find_packages
import os

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="eve-bus",
    version="0.1.2",
    author="Ray",
    author_email="ray@rayainfo.cn",
    description="A lightweight event bus implementation using Redis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DotNetAge/eve-bus",
    package_dir={"": "."},
    packages=find_packages(include=["eve"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "redis>=5.0.0",
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.1",
        "dependency-injector>=4.41.0",
    ],
)
