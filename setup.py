from setuptools import setup
import os


def get_version(path):
    fn = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        path, "__init__.py")
    with open(fn) as f:
        for line in f:
            if '__version__' in line:
                parts = line.split("=")
                return parts[1].split("'")[1]


here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst'), 'rb').read().decode('utf-8')
CHANGELOG = open(os.path.join(here, 'CHANGELOG.rst'), 'rb').read().decode('utf-8')


setup(
    name="devpi-pr",
    description="devpi-pr: a push request workflow plugin for devpi-server and devpi-client",
    long_description=README + "\n\n" + CHANGELOG,
    url="http://doc.devpi.net",
    version=get_version(os.path.join("src", "devpi_pr")),
    license="MIT",
    entry_points={
        'devpi_client': [
            "devpi-pr = devpi_pr.main"],
        'devpi_server': [
            "devpi-pr = devpi_pr.main"]},
    install_requires=[],
    include_package_data=True,
    zip_safe=False,
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*",
    package_dir={"": "src"},
    packages=['devpi_pr'])
