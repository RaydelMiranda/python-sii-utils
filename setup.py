""" CNS SII Management and Convenience Utilities
"""
from setuptools import setup, find_packages


cfg = {
    'name'             : 'python-sii-utils',
    'long_description' : __doc__,
    'version'          : '1.1.0.dev2016072200',
    'packages'         : find_packages('src'),
    'package_dir'      : {'': 'src'},

    'namespace_packages': ['sii'],

    'install_requires': [
        'docopt     >= 0.6.2',
        'python-sii >= 1.0.0',
    ],

    'entry_points': {
        'console_scripts': [
            'sii = sii.bin.main:main'
        ]
    },

    'dependency_links' : [],
    'zip_safe'         : False
}


if __name__ == '__main__':
    setup(**cfg)
