from setuptools import setup, find_packages

setup(
    name="ceragon-tfs-adapter",
    version="1.0.0",
    description="TeraFlowSDN (TFS) Device Adapter for Ceragon Wireless Transport Devices via REST/RESTCONF",
    author="Ceragon Intent Team",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
        "urllib3>=1.26.0",
        "click>=8.0.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "ceragon-tfs-adapter=ceragon_tfs_adapter.cli:main",
        ],
    },
    python_requires=">=3.9",
)
