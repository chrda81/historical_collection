import io
import os
import re

from setuptools import find_packages
from setuptools import setup


def read(filename):
    filename = os.path.join(os.path.dirname(__file__), filename)
    text_type = type(u"")
    with io.open(filename, mode="r", encoding="utf-8") as fd:
        return re.sub(text_type(r":[a-z]+:`~?(.*?)`"), text_type(r"``\1``"), fd.read())


setup(
    name="historical_collection",
    version="0.1.0",
    url="https://gitlab.com/srcrr/historical_collection",
    license="MIT",
    author="Jordan Hewitt",
    author_email="srcrr@opayq.com",
    description="Easily keep track of changes to Mongo document changes with a collection.",
    long_description=read("README.rst"),
    packages=find_packages(exclude=("tests",)),
    install_requires="pymongo".split(" "),
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
)
