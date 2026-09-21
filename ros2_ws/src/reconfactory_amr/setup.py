from glob import glob

from setuptools import find_packages, setup

setup(
    name="reconfactory_amr",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/reconfactory_amr"]),
        ("share/reconfactory_amr", ["package.xml"]),
        *[
            (f"share/reconfactory_amr/{folder}", glob(f"{folder}/*"))
            for folder in ("launch", "config", "urdf", "rviz", "maps")
        ],
    ],
    install_requires=["setuptools"],
    entry_points={"console_scripts": ["amr_manager = reconfactory_amr.manager:main"]},
)
