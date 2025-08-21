from setuptools import setup, find_packages
import os

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# 确保我们包含所有子包和数据文件
def package_data_dirs(package, roots):
    """Get the data directories for the package."""
    dirs = []
    for root in roots:
        for dirpath, _, _ in os.walk(os.path.join(package, root)):
            dirs.append(os.path.relpath(dirpath, package))
    return dirs

setup(
    name="eve-bus",
    version="0.1.1",
    author="Ray",
    author_email="ray@rayainfo.cn",
    description="A lightweight event bus implementation using Redis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DotNetAge/eve-bus",
    package_dir={"": "."},
    packages=find_packages(include=["eve", "eve.*"]),
    package_data={
        "eve": package_data_dirs("eve", ["adapters", "domain", "ports"])
    },
    include_package_data=True,
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
