from setuptools import setup, find_packages

install_requires = [
    'PyYAML >= 3.10, < 4',
    'GitPython >= 2.1, < 3',
]

setup(
    name='ms',
    description='CLI for developing microservices with Docker',
    version='0.1',
    author='ZeroCater',
    packages=find_packages(),
    install_requires=install_requires,
    entry_points={
        'console_scripts': ['ms=ms.main:main']
    }
)
