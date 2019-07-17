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
    description="devpi-pr: a pull request workflow plugin for devpi-server and devpi-client",
    long_description=README + "\n\n" + CHANGELOG,
    url="http://doc.devpi.net",
    version=get_version(os.path.join("src", "devpi_pr")),
    license="MIT",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        "Programming Language :: Python :: Implementation :: PyPy"] + [
            ("Programming Language :: Python :: %s" % x)
            for x in "3.5 3.6 3.7".split()],
    entry_points={
        'devpi_client': [
            "devpi-pr = devpi_pr.client"],
        'devpi_server': [
            "devpi-pr = devpi_pr.server"]},
    install_requires=[
        "appdirs",
        "attrs"],
    extras_require={
        'dev': [
            'pytest',
            'pytest-cov',
            'pytest-flake8',
            'webtest'],
        'client': [
            'devpi-client>=4.3.0'],
        'server': [
            'devpi-server>=5.0.0']},
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.5",
    package_dir={"": "src"},
    packages=['devpi_pr'])
