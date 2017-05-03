from distutils.core import setup

setup(
        name='ddosa-client',
        version='1.0',
        py_modules= ['ddosaclient'],
        package_data     = {
            "": [
                "*.txt",
                "*.md",
                "*.rst",
                "*.py"
                ]
            },
        license='Creative Commons Attribution-Noncommercial-Share Alike license',
        long_description=open('README.md').read(),
        )
