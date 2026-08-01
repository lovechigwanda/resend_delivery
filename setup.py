from setuptools import find_packages, setup

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

with open("resend_delivery/__init__.py", encoding="utf-8") as f:
	version = f.read().split("__version__ = ")[1].strip().strip('"').strip("'")

setup(
	name="resend_delivery",
	version=version,
	description="Send outgoing Frappe emails through Resend (resend.com) using per-account API keys.",
	author="Your Organisation",
	author_email="you@example.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)
