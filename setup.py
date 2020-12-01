import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="bitpost",
    version="1.1.3",
    author="Pedro FR",
    author_email="pedro@bitpost.co",
    description="Wrapper for the bitpost API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bitpostAPI/interface-pypi.org",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=['bit>=0.7.2', 'requests']
)