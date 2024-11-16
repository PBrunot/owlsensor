from setuptools import setup, find_packages

setup(name='owlsensor',
      version='0.1',
      description='Library to read data from OWL Energy meters',
      url='https://github.com/PBrunot/owlsensor',
      author='Pascal Brunot',
      author_email='pbr-dev@gmail.com',
      license='MIT',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'Topic :: System :: Hardware :: Hardware Drivers',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5'
      ],
      packages=find_packages(),
      install_requires=['pyserial>=3'],
      keywords='serial owl cm160 energy_meter homeautomation',
      zip_safe=False)
