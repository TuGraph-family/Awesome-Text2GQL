from setuptools import find_packages, setup
from typing import Dict, List
from collections import OrderedDict


class SetupSpec:
    def __init__(self) -> None:
        self.extras: Dict[str, List[str]] = {}
        self.install_requires: List[str] = []

    @property
    def unique_extras(self) -> Dict[str, List[str]]:
        unique_extras = OrderedDict()
        for k, v in self.extras.items():
            unique_extras[k] = list(set(v))
        return unique_extras


setup_spec = SetupSpec()


def core_dependencies():
    setup_spec.extras["core"] = [
        "antlr4-python3-runtime==4.13.2",
        "graphviz==0.20.1",
        "dashscope",
        "tqdm",
        "torch",
        "transformers",
    ]


def init_install_requires():
    setup_spec.install_requires += setup_spec.extras["core"]
    print(f"Install requires: \n{','.join(setup_spec.install_requires)}")


core_dependencies()
init_install_requires()

excluded_packages = ["tests", "*.tests", "*.tests.*", "examples"]

setup(
    name="Awesome-Text2GQL",
    author="Berry",
    author_email="panghy1106@163.com",
    description="Awesome-Text2GQL",
    packages=find_packages(exclude=excluded_packages),
    install_requires=setup_spec.install_requires,
    extras_require=setup_spec.unique_extras,
    python_requires=">=3.10",
)
