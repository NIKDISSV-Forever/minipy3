import setuptools

with open('README.md', encoding='UTF-8') as f:
    readme = f.read()

setuptools.setup(
    name="minipy3",
    version="1.0.0",
    description="Minimizes Python3 code",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Nikita (NIKDISSV)",
    author_email='nikdissv@proton.me',
    project_urls={
        'GitHub': 'https://github.com/NIKDISSV-Forever/minipy3',
    },
    packages=['minipy3'],
    license='MIT',
    python_requires='>=3.9',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Environment :: Console',
        'Topic :: Software Development :: Code Generators',
        'Topic :: System :: Archiving :: Compression',
        'License :: OSI Approved',
        'License :: OSI Approved :: MIT License',
    ],
    keywords=['minipy', 'minimize', 'code', '.min.py', 'compress'],
)
